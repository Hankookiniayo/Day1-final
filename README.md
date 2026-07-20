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
API         행수    CSV쓰기     PQ쓰기    CSV읽기     PQ읽기    CSV용량     PQ용량
--------------------------------------------------------------------
weather     72     3.30   842.35     1.20  1346.91     1.81     3.36
country      1     0.53     1.13     0.44     1.28     0.14     4.88
ip           1     0.55     0.53     0.32     0.94     0.12     4.68
```
(쓰기/읽기 단위 ms, 용량 KB)

## 5. Code 분석 결과에 대한 본인 의견

### 성능 측정 해석
- **Parquet 첫 쓰기/읽기(weather 842ms·1347ms)는 실제 I/O 비용이 아니라 pyarrow 엔진 최초 로딩 비용**이다. 이어지는 country·ip 처리에서는 Parquet도 1ms 안팎으로 떨어지는 것으로 확인된다. 즉 첫 호출 1회를 "워밍업"으로 빼고 보면 두 형식의 순수 I/O 차이는 이 정도 소규모 데이터에서는 미미하다.
- **용량**은 소규모 데이터에서 오히려 CSV가 작다(Parquet는 메타데이터·스키마 오버헤드가 고정적으로 붙기 때문). 데이터가 수만 행 이상으로 커지면 Parquet의 컬럼 압축이 효과를 내어 역전된다.
- 결론: **소량·1회성 데이터는 CSV, 대용량·반복 조회 데이터는 Parquet**가 유리하다.

### 코드 품질 측면 의견 (개선 사항)
- 현재는 검증 실패 시 해당 API를 통째로 건너뛴다. 실무에서는 **부분 실패 레코드만 격리(quarantine)** 하고 나머지는 저장하는 편이 데이터 손실이 적다.
- 벤치마크는 1회 측정이라 편차가 크다. **N회 반복 후 중앙값** 사용, pyarrow 워밍업 1회 제외를 적용하면 비교가 더 공정하다.
- API URL·좌표가 코드에 하드코딩되어 있다. 설정 파일(.env / config)로 분리하면 재사용성이 올라간다.
- 재시도(retry)·타임아웃 정책이 단순하다. 실서비스라면 **지수 백오프 재시도**를 넣는 것이 안전하다.

## 6. 채점 기준 대응 요약

| 항목 | 대응 |
|------|------|
| venv + requirements 설치 | `.venv` 활성화, requirements.txt 관리 |
| asyncio.gather 3개 동시 수집 | `collector.collect_all()` |
| Pydantic v2 + 예외처리 | `models.py`, `pipeline.validate()` try/except |
| CSV·Parquet 저장 + 성능 측정 | `storage.save_and_benchmark()` |
| pytest 통과 | 9건 통과 |
| ruff 무오류 | `All checks passed!` |
| 주석 | 전 파일 표준 머리말 + 함수 docstring |
| Git 커밋 | 로컬 커밋 이력 |
