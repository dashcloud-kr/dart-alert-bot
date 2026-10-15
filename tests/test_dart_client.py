"""DART 클라이언트 테스트 (respx 모킹)."""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest
import respx

from app.clients.dart import BASE_URL, DartClient, DartError

CORP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>00164779</corp_code><corp_name>삼성물산</corp_name><stock_code>028260</stock_code><modify_date>20240101</modify_date></list>
<list><corp_code>00999999</corp_code><corp_name>비상장회사</corp_name><stock_code></stock_code><modify_date>20240101</modify_date></list>
</result>"""

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result><status>010</status><message>등록되지 않은 키입니다.</message></result>"""


def make_zip(xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return buffer.getvalue()


def disclosure_row(
    rcept_no: str = "20261015000123",
    corp_code: str = "00126380",
    corp_name: str = "삼성전자",
    report_nm: str = "주요사항보고서(자기주식취득결정)",
    rcept_dt: str = "20261015",
    flr_nm: str = "삼성전자",
) -> dict:
    return {
        "rcept_no": rcept_no,
        "corp_code": corp_code,
        "corp_name": corp_name,
        "report_nm": report_nm,
        "rcept_dt": rcept_dt,
        "flr_nm": flr_nm,
    }


@pytest.fixture
def http():
    return httpx.AsyncClient()


@respx.mock
async def test_기업코드_다운로드와_파싱(http):
    respx.get(f"{BASE_URL}/corpCode.xml").mock(
        return_value=httpx.Response(200, content=make_zip(CORP_XML))
    )
    client = DartClient(http, "test-key")
    companies = await client.fetch_corp_codes()

    assert len(companies) == 3
    assert companies[0].corp_code == "00126380"
    assert companies[0].corp_name == "삼성전자"
    assert companies[0].stock_code == "005930"
    assert companies[2].stock_code == ""


@respx.mock
async def test_기업코드_키오류는_예외(http):
    respx.get(f"{BASE_URL}/corpCode.xml").mock(
        return_value=httpx.Response(200, content=ERROR_XML.encode())
    )
    client = DartClient(http, "bad-key")
    with pytest.raises(DartError, match="등록되지 않은 키"):
        await client.fetch_corp_codes()


@respx.mock
async def test_공시_목록_파싱(http):
    payload = {
        "status": "000",
        "message": "정상",
        "page_no": 1,
        "page_count": 100,
        "total_count": 1,
        "total_page": 1,
        "list": [disclosure_row()],
    }
    route = respx.get(f"{BASE_URL}/list.json").mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = DartClient(http, "test-key")
    disclosures = await client.list_disclosures("20261015", "20261015")

    assert len(disclosures) == 1
    item = disclosures[0]
    assert item.rcept_no == "20261015000123"
    assert item.report_nm == "주요사항보고서(자기주식취득결정)"
    assert item.url.endswith("rcpNo=20261015000123")
    params = route.calls[0].request.url.params
    assert params["bgn_de"] == "20261015"
    assert params["crtfc_key"] == "test-key"


@respx.mock
async def test_공시_페이지_순회(http):
    page1 = {
        "status": "000",
        "total_page": 2,
        "list": [disclosure_row("R1")],
    }
    page2 = {
        "status": "000",
        "total_page": 2,
        "list": [disclosure_row("R2")],
    }
    respx.get(f"{BASE_URL}/list.json").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
    )
    client = DartClient(http, "test-key")
    disclosures = await client.list_disclosures("20261015", "20261015")
    assert [d.rcept_no for d in disclosures] == ["R1", "R2"]


@respx.mock
async def test_공시_데이터없음은_빈_목록(http):
    payload = {"status": "013", "message": "조회된 데이타가 없습니다."}
    respx.get(f"{BASE_URL}/list.json").mock(return_value=httpx.Response(200, json=payload))
    client = DartClient(http, "test-key")
    assert await client.list_disclosures("20261015", "20261015") == []


@respx.mock
async def test_공시_오류_상태는_예외(http):
    payload = {"status": "020", "message": "요청 제한을 초과하였습니다."}
    respx.get(f"{BASE_URL}/list.json").mock(return_value=httpx.Response(200, json=payload))
    client = DartClient(http, "test-key")
    with pytest.raises(DartError, match="020"):
        await client.list_disclosures("20261015", "20261015")


@respx.mock
async def test_HTTP_오류는_예외(http):
    respx.get(f"{BASE_URL}/list.json").mock(return_value=httpx.Response(500))
    client = DartClient(http, "test-key")
    with pytest.raises(httpx.HTTPStatusError):
        await client.list_disclosures("20261015", "20261015")
