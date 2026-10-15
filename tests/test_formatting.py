"""공시 메시지 포맷 테스트."""

from __future__ import annotations

from app.services.formatting import format_date, format_disclosure, format_morning
from app.services.repository import DisclosureRecord


def make_record(
    corp_name: str = "삼성전자",
    report_nm: str = "주요사항보고서(자기주식취득결정)",
    flr_nm: str = "삼성전자",
    rcept_dt: str = "20261015",
) -> DisclosureRecord:
    return DisclosureRecord(
        rcept_no="20261015000123",
        corp_code="00126380",
        corp_name=corp_name,
        report_nm=report_nm,
        rcept_dt=rcept_dt,
        flr_nm=flr_nm,
    )


def test_날짜_포맷():
    assert format_date("20261015") == "10/15"
    assert format_date("invalid") == "invalid"


def test_공시_메시지():
    text = format_disclosure(make_record())
    assert "[공시] 삼성전자" in text
    assert "주요사항보고서(자기주식취득결정)" in text
    assert "접수 10/15" in text
    assert "제출" not in text  # 제출인이 기업명과 같으면 생략
    assert "rcpNo=20261015000123" in text


def test_공시_메시지_제출인_다르면_표시():
    text = format_disclosure(make_record(flr_nm="금융감독원"))
    assert "제출 금융감독원" in text


def test_아침_요약():
    chunks = format_morning("10/14", [make_record(), make_record("SK하이닉스")])
    assert len(chunks) == 1
    text = chunks[0]
    assert "어제(10/14) 관심기업 공시 2건" in text
    assert "삼성전자" in text
    assert "SK하이닉스" in text
