# ----------------------------------------------------------------------------
# 작성자   : 광주캠퍼스_2반_정구현
# 작성목적 : 수집→검증→저장→성능비교 전체 흐름을 실행하는 파이프라인 진입점
# 작성일   : 2026-07-20
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#   2026-07-20 | 최초작성 | collector/models/storage 를 엮는 main 파이프라인 작성
#   2026-07-20 | 내결함성 | 수집 단계에서 누락된 API 를 검증 전에 명확히 로그로 구분
#   2026-07-20 | 린트대응 | ruff I001 import 정렬 자동 정리
#   2026-07-20 | 확장성   | validate() 의 API별 반복 if 를 SOURCES 순회 for 루프로 통합
# ----------------------------------------------------------------------------
"""데이터 미니 수집 파이프라인 진입점.

흐름:
    1) collector.collect_all()  : 3개 API 동시 수집(asyncio.gather)
    2) models.parse_*()         : Pydantic v2 로 타입·범위 검증
    3) storage.save_and_benchmark() : CSV/Parquet 저장 및 성능 측정
    4) storage.print_benchmark_table() : 비교 결과 출력

검증 단계에서 오류가 나면 해당 API 는 건너뛰고 나머지는 계속 처리한다.
"""

from __future__ import annotations

import asyncio

import pandas as pd
from pydantic import ValidationError

from src import storage
from src.collector import collect_all
from src.models import SOURCES


def validate(raw: dict[str, dict]) -> dict[str, pd.DataFrame]:
    """원본 JSON 묶음을 검증하여 {이름: DataFrame} 으로 변환한다.
    개별 API 검증이 실패하면 예외를 잡아 로그를 남기고 그 API 만 제외한다.

    API별로 분기하지 않고 models.SOURCES(각 API를 표현한 ApiSource 목록)를
    순회한다. API 가 늘어나도 SOURCES 에 한 줄 추가하면 되고, 이 함수는
    수정할 필요가 없다.
    """
    frames: dict[str, pd.DataFrame] = {}

    for source in SOURCES:
        # 수집 단계에서 빠진 API 는 검증을 건너뛰고 명확히 로그를 남긴다.
        if source.name not in raw:
            print(f"  [검증 생략] {source.name} : 수집 단계에서 누락됨")
            continue

        try:
            # 파서는 레코드 리스트를 돌려주므로 weather(다건)·country/ip(1건)를 동일하게 처리한다.
            records = source.parse(raw[source.name])
            frames[source.name] = pd.DataFrame([r.model_dump() for r in records])
            print(f"  [검증] {source.name} : {len(records)}건 통과")
        except (ValidationError, KeyError, ValueError) as exc:
            print(f"  [검증 실패] {source.name} : {exc}")

    return frames


async def run() -> None:
    """파이프라인 전체를 순서대로 실행한다."""
    # 1) 수집
    raw = await collect_all()

    # 2) 검증
    print("\n[pipeline] 스키마 검증 (Pydantic v2)")
    frames = validate(raw)

    # 3) 저장 + 성능 측정
    stats = [storage.save_and_benchmark(name, df) for name, df in frames.items()]

    # 4) 결과 출력
    storage.print_benchmark_table(stats)
    print("\n[pipeline] 완료 — 결과물은 data/ 폴더에 저장되었습니다.")


def main() -> None:
    """스크립트 실행 진입점 (asyncio 이벤트 루프 구동)."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
