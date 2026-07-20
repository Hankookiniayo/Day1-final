# ----------------------------------------------------------------------------
# 작성자   : 광주캠퍼스_2반_정구현
# 작성목적 : asyncio + httpx 로 3개 API를 동시에 수집하는 비동기 수집기
# 작성일   : 2026-07-20
#
# 본 파일은 KDT 교육을 위한 Sample 코드이므로 작성자에게 모든 저작권이 있습니다.
#
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#   2026-07-20 | 최초작성 | asyncio.gather 기반 3개 API 동시 수집 함수 작성
# ----------------------------------------------------------------------------
"""asyncio.gather() 를 이용해 3개 API를 병렬로 호출하는 수집 계층.

- httpx.AsyncClient 하나를 공유해 커넥션을 재사용한다.
- 각 요청은 코루틴으로 만들고 asyncio.gather 로 동시에 실행한다.
- 이 계층은 "원본 JSON 을 가져오는 것"까지만 책임진다(검증은 models 계층).
"""

from __future__ import annotations

import asyncio
import time

import httpx

# 수집 대상 3개 API (API_ref/api_ref.txt 기준)
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


async def fetch_json(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, dict]:
    """단일 API를 호출해 (이름, JSON dict) 를 반환하는 코루틴.

    HTTP 상태 코드가 4xx/5xx 이면 raise_for_status() 로 예외를 발생시킨다.
    """
    started = time.perf_counter()
    response = await client.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    elapsed = time.perf_counter() - started
    # 개별 응답이 정상적으로 도착했음을 로그로 남긴다.
    print(f"  [OK] {name:<8} status={response.status_code} ({elapsed:.3f}s)")
    return name, response.json()


async def collect_all() -> dict[str, dict]:
    """3개 API를 asyncio.gather 로 동시에 수집해 {이름: 원본 JSON} 을 반환한다."""
    print("[collector] 3개 API 동시 수집 시작 (asyncio.gather)")
    started = time.perf_counter()

    async with httpx.AsyncClient() as client:
        # 각 API 호출을 코루틴 목록으로 만든 뒤 gather 로 병렬 실행한다.
        tasks = [fetch_json(client, name, url) for name, url in API_URLS.items()]
        results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - started
    print(f"[collector] 동시 수집 완료 (총 {elapsed:.3f}s, {len(results)}건)")

    # (이름, JSON) 튜플 목록을 dict 로 정리해 반환한다.
    return dict(results)
