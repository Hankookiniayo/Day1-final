# ----------------------------------------------------------------------------
# 작성자   : 광주캠퍼스_2반_정구현
# 작성목적 : asyncio + httpx 로 3개 API를 동시에 수집하는 비동기 수집기
# 작성일   : 2026-07-20
#
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#   2026-07-20 | 최초작성 | asyncio.gather 기반 3개 API 동시 수집 함수 작성
#   2026-07-20 | 내결함성 | gather(return_exceptions=True) 로 일부 API 실패 시에도 나머지 수집
#   2026-07-20 | 재시도추가 | retry_async 데코레이터로 일시적 오류 시 지수 백오프 재시도
# ----------------------------------------------------------------------------
"""asyncio.gather() 를 이용해 3개 API를 병렬로 호출하는 수집 계층.

- httpx.AsyncClient 하나를 공유해 커넥션을 재사용한다.
- 각 요청은 코루틴으로 만들고 asyncio.gather 로 동시에 실행한다.
- 각 요청은 retry_async 데코레이터로 일시적 오류 시 자동 재시도한다.
- 일부 API 가 실패해도 gather(return_exceptions=True) 로 나머지는 계속 수집한다.
- 이 계층은 "원본 JSON 을 가져오는 것"까지만 책임진다(검증은 models 계층).
"""

from __future__ import annotations
import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar
import httpx

# retry_async 의 타입 힌트용: 감싸는 원본 코루틴의 인자/반환 타입을 그대로 보존한다.
P = ParamSpec("P")
T = TypeVar("T")

# 수집 대상 3개 API를 dict형식으로 정의한다. (이름: URL)
API_URLS: dict[str, str] = {
    # Open-Meteo : 서울 3일 시간대별 기온·강수확률
    "weather": (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=37.5665&longitude=126.9780"
        "&hourly=temperature_2m,precipitation_probability"
        "&forecast_days=3&timezone=Asia/Seoul"
    ),
    # countries.dev : 대한민국 국가 정보
    "country": "https://countries.dev/alpha/KOR",
    # ip-api : IP 기반 지역 정보
    "ip": "http://ip-api.com/json/8.8.8.8",
}

# 요청 타임아웃(초)
REQUEST_TIMEOUT = 10.0

# 재시도 대상으로 볼 "일시적" 예외.
# httpx.TransportError 는 연결 실패·타임아웃 등 네트워크 계층 오류를 포괄한다.
# 반면 4xx(예: 400 Bad Request)는 재시도해도 결과가 같으므로 대상에서 제외한다.
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (httpx.TransportError,)


def retry_async(
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    exceptions: tuple[type[Exception], ...] = TRANSIENT_ERRORS,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """비동기 함수가 지정한 예외로 실패하면 지수 백오프로 재시도하는 데코레이터.

    - retries    : 최초 시도 뒤 추가로 재시도할 횟수 (총 시도 = retries + 1).
    - base_delay : 첫 재시도 전 대기(초). 재시도마다 2배씩 늘린다(지수 백오프).
    - exceptions : 재시도 대상 예외 종류. 그 외 예외(예: 4xx)는 즉시 전파한다.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            attempt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    attempt += 1
                    # 재시도 횟수를 모두 소진하면 마지막 예외를 그대로 올린다.
                    if attempt > retries:
                        raise
                    delay = base_delay * 2 ** (attempt - 1)
                    print(
                        f"  [재시도] {func.__name__} {attempt}/{retries}회 "
                        f"({type(exc).__name__}) — {delay:.1f}s 후 재시도"
                    )
                    await asyncio.sleep(delay)

        return wrapper

    return decorator


@retry_async(retries=3, base_delay=0.5)
async def fetch_json(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, dict]:
    """단일 API를 호출해 (이름, JSON dict) 를 반환하는 코루틴.

    HTTP 상태 코드가 4xx/5xx 이면 raise_for_status() 로 예외를 발생시킨다.
    네트워크·타임아웃 등 일시적 오류는 retry_async 가 자동으로 재시도한다.
    """
    started = time.perf_counter()
    response = await client.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    elapsed = time.perf_counter() - started
    # 개별 응답이 정상적으로 도착했음을 로그로 남긴다.
    print(f"  [OK] {name:<8} status={response.status_code} ({elapsed:.3f}s)")
    return name, response.json()


async def collect_all() -> dict[str, dict]:
    """3개 API를 asyncio.gather 로 동시에 수집해 {이름: 원본 JSON} 을 반환한다.

    return_exceptions=True 로 두어 한 API 가 실패해도 예외가 전파되지 않고,
    실패한 API 만 로그로 남긴 뒤 결과 dict 에서 제외한다(나머지는 정상 반환).
    """
    print("[collector] 3개 API 동시 수집 시작 (asyncio.gather)")
    started = time.perf_counter()

    async with httpx.AsyncClient() as client:
        # 각 API 호출을 코루틴 목록으로 만든 뒤 gather 로 병렬 실행한다.
        tasks = [fetch_json(client, name, url) for name, url in API_URLS.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 성공/실패를 분리한다. tasks 는 API_URLS 순서와 같으므로 이름을 짝지어 판별한다.
    collected: dict[str, dict] = {}
    for name, result in zip(API_URLS, results, strict=True):
        if isinstance(result, Exception):
            # 실패한 API 는 건너뛰고, 나머지 수집은 계속한다.
            print(f"  [실패] {name:<8} {type(result).__name__}: {result}")
            continue
        _, payload = result
        collected[name] = payload

    elapsed = time.perf_counter() - started
    print(
        f"[collector] 동시 수집 완료 "
        f"(총 {elapsed:.3f}s, 성공 {len(collected)}/{len(API_URLS)}건)"
    )
    return collected
