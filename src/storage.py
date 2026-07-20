# ----------------------------------------------------------------------------
# 작성자   : 광주캠퍼스_2반_정구현
# 작성목적 : 검증 통과 데이터를 CSV/Parquet 로 저장하고 읽기·쓰기 성능을 비교
# 작성일   : 2026-07-20
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#   2026-07-20 | 최초작성 | CSV/Parquet 저장 및 읽기/쓰기 시간 측정·비교 함수 작성
#   2026-07-20 | 출력정렬 | 한글(전각) 헤더가 어긋나던 표를 표시 폭 기준 정렬로 수정
# ----------------------------------------------------------------------------
"""검증을 통과한 레코드를 DataFrame 으로 만들어 두 형식으로 저장하고,
각 형식의 쓰기/읽기 시간을 측정해 비교 결과를 반환하는 저장 계층.
"""

from __future__ import annotations

import time
import unicodedata
from pathlib import Path

import pandas as pd

# 저장 결과가 쌓이는 폴더
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

#터미널 표시 폭을 계산
def _disp_len(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)

#터미널 표시 폭 기준으로 공백을 채워 정렬한다. (align='>' 오른쪽, '<' 왼쪽)
def _pad(text: str, width: int, align: str = ">") -> str:

    gap = max(0, width - _disp_len(text))
    return " " * gap + text if align == ">" else text + " " * gap


def _measure(func) -> tuple[object, float]:
    """func() 를 실행하고 (결과, 소요시간초) 를 반환하는 작은 헬퍼."""
    started = time.perf_counter()
    result = func()
    return result, time.perf_counter() - started


def save_and_benchmark(name: str, df: pd.DataFrame) -> dict:
    """DataFrame 을 CSV/Parquet 로 저장하고 읽기/쓰기 시간을 측정한다.

    반환값 예:
        {"name", "rows", "csv_write", "csv_read", "parquet_write", "parquet_read",
         "csv_size", "parquet_size"}
    """
    DATA_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / f"{name}.csv"
    parquet_path = DATA_DIR / f"{name}.parquet"

    # --- 쓰기 시간 측정 ---
    _, csv_write = _measure(lambda: df.to_csv(csv_path, index=False, encoding="utf-8-sig"))
    _, parquet_write = _measure(lambda: df.to_parquet(parquet_path, index=False))

    # --- 읽기 시간 측정 ---
    _, csv_read = _measure(lambda: pd.read_csv(csv_path))
    _, parquet_read = _measure(lambda: pd.read_parquet(parquet_path))

    return {
        "name": name,
        "rows": len(df),
        "csv_write": csv_write,
        "csv_read": csv_read,
        "parquet_write": parquet_write,
        "parquet_read": parquet_read,
        "csv_size": csv_path.stat().st_size,
        "parquet_size": parquet_path.stat().st_size,
    }


def print_benchmark_table(stats: list[dict]) -> None:
    """성능 측정 결과를 표 형태로 출력한다(단위: ms, KB)."""
    print("\n[storage] CSV vs Parquet 성능 비교 (쓰기/읽기: ms, 용량: KB)")
    header = (
        f"{_pad('API', 8, '<')} {_pad('행수', 5)} "
        f"{_pad('CSV쓰기', 8)} {_pad('PQ쓰기', 8)} {_pad('CSV읽기', 8)} {_pad('PQ읽기', 8)} "
        f"{_pad('CSV용량', 8)} {_pad('PQ용량', 8)}"
    )
    print(header)
    print("-" * _disp_len(header))
    for s in stats:
        print(
            f"{s['name']:<8} {s['rows']:>5} "
            f"{s['csv_write'] * 1000:>8.2f} {s['parquet_write'] * 1000:>8.2f} "
            f"{s['csv_read'] * 1000:>8.2f} {s['parquet_read'] * 1000:>8.2f} "
            f"{s['csv_size'] / 1024:>8.2f} {s['parquet_size'] / 1024:>8.2f}"
        )
