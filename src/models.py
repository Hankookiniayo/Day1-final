# ----------------------------------------------------------------------------
# 작성자   : 광주캠퍼스_2반_정구현
# 작성목적 : 3개 API 응답을 검증하기 위한 Pydantic v2 모델 정의 (타입·범위 검증)
# 작성일   : 2026-07-20
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#   2026-07-20 | 최초작성 | Weather/Country/Ip 3종 Pydantic 모델 및 파서 작성
#   2026-07-20 | 린트대응 | zip(strict=True) 명시, IpRecord countryCode 정규화 검증기 추가
#   2026-07-20 | 린트대응 | ruff I001 import 정렬 자동 정리
#   2026-07-20 | 확장성   | ApiSource 레지스트리(SOURCES) 도입 — API 추가를 한 곳으로 모음
# ----------------------------------------------------------------------------
"""수집한 JSON에서 필요한 필드만 추출하여 타입·범위를 검증하는 Pydantic 모델 모음.

각 모델은 다음 원칙을 따른다.
- 필요한 필드만 명시적으로 선언한다(불필요한 필드는 무시).
- Field 제약(ge/le 등)으로 값의 범위를 검증한다.
- 검증 실패 시 pydantic.ValidationError 가 발생하며, 파이프라인에서 이를 처리한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator


# ----------------------------------------------------------------------------
# 1) Open-Meteo : 서울 3일 시간대별 기온·강수확률
#    - 응답은 hourly.{time[], temperature_2m[], precipitation_probability[]} 형태의
#      "배열들의 묶음" 이므로, 시각 단위 레코드(WeatherRecord)로 평탄화(flatten)한다.
# ----------------------------------------------------------------------------
class WeatherRecord(BaseModel):
    """한 시각의 기온·강수확률 레코드."""

    time: str = Field(..., description="ISO8601 시각 문자열 (예: 2026-07-20T00:00)")
    temperature_2m: float = Field(..., ge=-90.0, le=60.0, description="지상 2m 기온(℃)")
    precipitation_probability: int = Field(..., ge=0, le=100, description="강수확률(%)")


def parse_weather(payload: dict) -> list[WeatherRecord]:
    """Open-Meteo 원본 JSON을 WeatherRecord 리스트로 변환한다.

    hourly 하위의 세 배열 길이가 다르면 스키마가 깨진 것으로 보고 예외를 발생시킨다.
    """
    hourly = payload["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    probs = hourly["precipitation_probability"]

    if not (len(times) == len(temps) == len(probs)):
        raise ValueError("Open-Meteo hourly 배열 길이가 서로 일치하지 않습니다.")

    # zip 으로 시각 단위 레코드를 만들고 각 레코드를 개별 검증한다.
    return [
        WeatherRecord(time=t, temperature_2m=temp, precipitation_probability=prob)
        for t, temp, prob in zip(times, temps, probs, strict=True)
    ]


# ----------------------------------------------------------------------------
# 2) countries.dev : 국가 정보(대한민국)
# ----------------------------------------------------------------------------
class CountryRecord(BaseModel):
    """국가 기본 정보 레코드."""

    name: str = Field(..., min_length=1, description="국가명(영문)")
    alpha3Code: str = Field(..., min_length=3, max_length=3, description="ISO alpha-3 코드")
    capital: str = Field(..., min_length=1, description="수도")
    region: str = Field(..., min_length=1, description="대륙(권역)")
    population: int = Field(..., ge=0, description="인구수")
    area: float = Field(..., gt=0, description="국토 면적(㎢)")
    population_density: float = Field(..., ge=0, description="인구밀도(명/㎢)")
    gini: float = Field(..., ge=0, le=100, description="지니계수")


def parse_country(payload: dict) -> CountryRecord:
    """countries.dev 원본 JSON을 CountryRecord 로 변환한다.
    응답 키(populationDensity)를 모델 필드(population_density)로 매핑한다.
    """
    return CountryRecord(
        name=payload["name"],
        alpha3Code=payload["alpha3Code"],
        capital=payload["capital"],
        region=payload["region"],
        population=payload["population"],
        area=payload["area"],
        population_density=payload["populationDensity"],
        gini=payload["gini"],
    )


# ----------------------------------------------------------------------------
# 3) ip-api : IP 기반 지역 정보
# ----------------------------------------------------------------------------
class IpRecord(BaseModel):
    """IP 위치 정보 레코드."""

    query: str = Field(..., min_length=1, description="조회한 IP 주소")
    country: str = Field(..., min_length=1, description="국가명")
    countryCode: str = Field(..., min_length=2, max_length=2, description="국가 코드")
    city: str = Field(..., min_length=1, description="도시")
    lat: float = Field(..., ge=-90.0, le=90.0, description="위도")
    lon: float = Field(..., ge=-180.0, le=180.0, description="경도")
    timezone: str = Field(..., min_length=1, description="시간대")
    isp: str = Field(..., min_length=1, description="인터넷 서비스 제공자")

    @field_validator("countryCode")
    @classmethod
    def _normalize_country_code(cls, v: str) -> str:
        """국가 코드는 대문자로 정규화한다(예: 'kr' -> 'KR')."""
        return v.upper()


def parse_ip(payload: dict) -> IpRecord:
    """ip-api 원본 JSON을 IpRecord 로 변환한다.
    status 필드가 'success' 가 아니면 조회 실패로 보고 예외를 발생시킨다.
    """
    status = payload.get("status")
    if status != "success":
        raise ValueError(f"ip-api 조회 실패: status={status!r}")

    return IpRecord(
        query=payload["query"],
        country=payload["country"],
        countryCode=payload["countryCode"],
        city=payload["city"],
        lat=payload["lat"],
        lon=payload["lon"],
        timezone=payload["timezone"],
        isp=payload["isp"],
    )


# ----------------------------------------------------------------------------
# API 소스 레지스트리
#   - 각 API를 "이름 + 파서" 를 묶은 ApiSource 객체로 표현한다.
#   - 파서는 원본 JSON을 '레코드 리스트' 로 통일해서 반환한다.
#       weather : 여러 레코드(시각 단위) -> 그대로 리스트
#       country / ip : 단일 레코드 -> 1개짜리 리스트로 감싼다
#   - 파이프라인은 이 리스트를 for 로 순회하므로, API가 늘어나도
#     아래 SOURCES 에 한 줄만 추가하면 된다(중복 if 분기 불필요).
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ApiSource:
    """수집 대상 API 하나: 이름과 '원본 JSON -> 레코드 리스트' 파서를 묶는다."""

    name: str
    parse: Callable[[dict], list[BaseModel]]


SOURCES: list[ApiSource] = [
    ApiSource("weather", parse_weather),
    ApiSource("country", lambda payload: [parse_country(payload)]),
    ApiSource("ip", lambda payload: [parse_ip(payload)]),
]
