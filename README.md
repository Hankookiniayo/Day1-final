# Day1 종합실습 — 데이터 미니 수집 파이프라인

광주캠퍼스 2반 정구현 · 2026-07-20

3개 공개 API를 **비동기로 동시 수집** → **Pydantic v2로 스키마 검증** → **CSV·Parquet 저장 및 성능 비교**하는 미니 파이프라인이다.

---

## 1. 프로젝트 구조

```
day1final/
├── API_ref/api_ref.txt      # 수집 대상 3개 API 참고
├── src/
│   ├── models.py            # Pydantic v2 모델 (타입·범위 검증)
│   ├── collector.py         # asyncio + httpx 동시 수집 (asyncio.gather)
│   ├── storage.py           # CSV/Parquet 저장 + 읽기·쓰기 시간 측정
│   └── pipeline.py          # 수집→검증→저장→비교 main
├── tests/test_models.py     # pytest 스키마 검증 테스트 (9건)
├── data/                    # 실행 결과물(csv/parquet)
├── requirements.txt         # 패키지 목록
└── pyproject.toml           # pytest / ruff 설정
```

## 2. 수집 대상 API (3종)

| 이름 | API | 내용 |
|------|-----|------|
| weather | Open-Meteo | 서울 3일 시간대별 기온·강수확률 (72개 시각) |
| country | countries.dev | 대한민국 국가 정보 (인구·면적·지니 등) |
| ip | ip-api | IP(8.8.8.8) 기반 지역 정보 |

## 3. 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.pipeline      # 파이프라인 실행
pytest -q                   # 테스트
ruff check .                # 스타일 검사
```

## 4. 실행 결과

### 4-1. 비동기 수집 (asyncio.gather)
```
[collector] 3개 API 동시 수집 시작 (asyncio.gather)
  [OK] ip       status=200 (0.161s)
  [OK] country  status=200 (0.353s)
  [OK] weather  status=200 (1.066s)
[collector] 동시 수집 완료 (총 1.104s, 3건)
```
- 3개 응답 시간이 각각 0.16 / 0.35 / 1.07초인데 **전체는 1.10초** → 순차 실행(합 약 1.58초)이 아니라 가장 느린 요청 시간에 수렴 = 동시 수집이 실제로 동작함을 확인.

### 4-2. 스키마 검증 (Pydantic v2)
```
  [검증] weather : 72건 통과
  [검증] country : 1건 통과
  [검증] ip : 1건 통과
```

### 4-3. CSV vs Parquet 성능 비교
```
API       행수  CSV쓰기   PQ쓰기  CSV읽기   PQ읽기  CSV용량   PQ용량
--------------------------------------------------------------------
weather     72     2.87    27.45     0.73    36.21     1.81     3.35
country      1     0.36     0.62     0.32     0.76     0.14     4.88
ip           1     0.28     0.49     0.30     0.61     0.12     4.68
```
(쓰기/읽기 단위 ms, 용량 KB)

## 5. Code 분석 결과에 대한 본인 의견

### 개선 사항
1. 스키마 검증 함수(`validate()`)가 `if` 체크 → `try/except` 구문의 반복 구조라서, 수집 API 개수가 늘어날수록 코드가 길어질 우려가 있다.
   - 각 API를 하나의 클래스로 정의하여 `if` 분기를 삭제하고 `for` 루프로 일괄 검증하도록 리팩터링할 수 있다.

### 개인 의견
1. 현재는 단일 프로세스로 작업했지만, API 개수가 증가하면 multiprocess 처리 또는 동시 실행 개수 제한 작업이 필요하다.
   - 데이터 용량이 커지면 `max_workers`, chunk 분할 등 병목 현상을 해결하는 코드를 추가해야 한다.
2. API URL의 재사용성 및 확장성이 미흡하다.
   - 현재는 API 키가 아닌 공개 URL 형태라 `.env` / `.gitignore`로 분리하지 않았다.
   - 규모 확장 시 API URL의 재사용성과 보안을 위해 `.env`로 분리하고 별도 설정 파일을 두는 편이 좋다.

### CSV vs Parquet 성능 측정 의견 및 분석
Parquet이 CSV보다 속도와 용량 측면에서 우수할 것이라 예상했으나, `weather` 데이터(Open-Meteo API)에서 Parquet이 CSV보다 매우 느린 성능을 보였다. 용량도 모든 API에서 `Parquet > CSV`로 나타났다.

- 원인 파악: Parquet 첫 쓰기/읽기는 실제 I/O 비용이 아니라 pyarrow 엔진 최초 로딩 비용이다.
  - 실제로 첫 대상인 `weather`는 PQ쓰기 27.45ms(CSV 2.87ms의 약 10배), PQ읽기 36.21ms(CSV 0.73ms의 약 50배)로 크게 튀었다.
  - 엔진 로딩 이후 처리되는 `country`·`ip` 데이터는 두 형식 모두 1ms 미만으로, **성능 차이가 미미**한 것을 확인했다.
- 용량: Parquet는 메타데이터·스키마 오버헤드가 고정적으로 붙는다. 따라서 소규모 데이터의 경우 CSV가 오히려 더 작은 용량을 나타냈다.
- 결론: 소량·1회성 데이터는 CSV, 대용량·반복 조회 데이터는 Parquet가 유리하다.
