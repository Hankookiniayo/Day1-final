# ----------------------------------------------------------------------------
# 작성자   : 광주캠퍼스_2반_정구현
# 작성목적 : Pydantic v2 스키마 검증 로직에 대한 pytest 단위 테스트
# 작성일   : 2026-07-20
#
# 본 파일은 KDT 교육을 위한 Sample 코드이므로 작성자에게 모든 저작권이 있습니다.
#
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#   2026-07-20 | 최초작성 | 정상/비정상 케이스 스키마 검증 테스트 작성
# ----------------------------------------------------------------------------
"""models.py 의 파서·모델이 타입/범위 검증을 올바로 수행하는지 확인한다.

- 정상 입력은 통과해야 한다.
- 범위를 벗어나거나 status 가 실패인 입력은 예외가 발생해야 한다.
"""

import pytest
from pydantic import ValidationError

from src.models import (
    CountryRecord,
    IpRecord,
    WeatherRecord,
    parse_ip,
    parse_weather,
)


# ---------------------------------------------------------------------------
# WeatherRecord
# ---------------------------------------------------------------------------
def test_weather_record_valid():
    """정상 기온·강수확률은 통과한다."""
    rec = WeatherRecord(time="2026-07-20T00:00", temperature_2m=23.2, precipitation_probability=6)
    assert rec.temperature_2m == 23.2
    assert rec.precipitation_probability == 6


def test_weather_precipitation_out_of_range():
    """강수확률(0~100) 범위를 벗어나면 ValidationError."""
    with pytest.raises(ValidationError):
        WeatherRecord(time="2026-07-20T00:00", temperature_2m=20.0, precipitation_probability=150)


def test_parse_weather_flattens_arrays():
    """hourly 배열을 시각 단위 레코드로 평탄화한다."""
    payload = {
        "hourly": {
            "time": ["2026-07-20T00:00", "2026-07-20T01:00"],
            "temperature_2m": [23.2, 22.9],
            "precipitation_probability": [6, 15],
        }
    }
    records = parse_weather(payload)
    assert len(records) == 2
    assert records[1].precipitation_probability == 15


def test_parse_weather_length_mismatch():
    """배열 길이가 다르면 ValueError."""
    payload = {
        "hourly": {
            "time": ["2026-07-20T00:00"],
            "temperature_2m": [23.2, 22.9],
            "precipitation_probability": [6],
        }
    }
    with pytest.raises(ValueError):
        parse_weather(payload)


# ---------------------------------------------------------------------------
# CountryRecord
# ---------------------------------------------------------------------------
def test_country_record_valid():
    """정상 국가 정보는 통과한다."""
    rec = CountryRecord(
        name="Korea (Republic of)",
        alpha3Code="KOR",
        capital="Seoul",
        region="Asia",
        population=51780579,
        area=100210.0,
        population_density=516.72,
        gini=31.4,
    )
    assert rec.alpha3Code == "KOR"
    assert rec.population > 0


def test_country_negative_population():
    """인구수가 음수이면 ValidationError."""
    with pytest.raises(ValidationError):
        CountryRecord(
            name="Testland",
            alpha3Code="TST",
            capital="Testcity",
            region="Asia",
            population=-1,
            area=100.0,
            population_density=1.0,
            gini=30.0,
        )


# ---------------------------------------------------------------------------
# IpRecord
# ---------------------------------------------------------------------------
def test_ip_record_normalizes_country_code():
    """countryCode 는 대문자로 정규화된다."""
    rec = IpRecord(
        query="8.8.8.8",
        country="United States",
        countryCode="us",
        city="Ashburn",
        lat=39.03,
        lon=-77.5,
        timezone="America/New_York",
        isp="Google LLC",
    )
    assert rec.countryCode == "US"


def test_parse_ip_status_fail():
    """status 가 success 가 아니면 ValueError."""
    payload = {"status": "fail", "message": "invalid query"}
    with pytest.raises(ValueError):
        parse_ip(payload)


def test_ip_latitude_out_of_range():
    """위도(-90~90) 범위를 벗어나면 ValidationError."""
    with pytest.raises(ValidationError):
        IpRecord(
            query="8.8.8.8",
            country="United States",
            countryCode="US",
            city="Ashburn",
            lat=999.0,
            lon=-77.5,
            timezone="America/New_York",
            isp="Google LLC",
        )
