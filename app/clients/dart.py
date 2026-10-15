"""DART(전자공시) OpenAPI 클라이언트."""

from __future__ import annotations

import io
import logging
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"

SUCCESS_CODES = {"000"}
NO_DATA_CODES = {"013"}

MAX_PAGES = 10


class DartError(RuntimeError):
    """DART API 오류 (키 오류·트래픽 초과 등)."""


@dataclass(frozen=True)
class CorpCode:
    corp_code: str
    corp_name: str
    stock_code: str  # 상장사만 값이 있고 비상장은 빈 문자열


@dataclass(frozen=True)
class Disclosure:
    rcept_no: str  # 접수번호
    corp_code: str
    corp_name: str
    report_nm: str  # 공시명
    rcept_dt: str  # 접수일자 YYYYMMDD
    flr_nm: str  # 제출인

    @property
    def url(self) -> str:
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"


class DartClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def fetch_corp_codes(self) -> list[CorpCode]:
        """전체 기업 고유번호 목록을 내려받아 파싱한다 (ZIP 응답)."""
        response = await self._http.get(
            f"{BASE_URL}/corpCode.xml", params={"crtfc_key": self._api_key}
        )
        response.raise_for_status()
        content = response.content

        if content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml_bytes = archive.read("CORPCODE.xml")
        else:
            # 키 오류 등은 XML 에러 응답으로 온다
            try:
                payload = ET.fromstring(content.decode("utf-8", errors="replace"))
                message = payload.findtext("message") or "알 수 없는 오류"
            except ET.ParseError:
                message = "corpCode 응답을 해석할 수 없습니다"
            raise DartError(f"DART 오류: {message}")

        root = ET.fromstring(xml_bytes)
        companies: list[CorpCode] = []
        for element in root.iter("list"):
            corp_code = (element.findtext("corp_code") or "").strip()
            corp_name = (element.findtext("corp_name") or "").strip()
            stock_code = (element.findtext("stock_code") or "").strip()
            if corp_code and corp_name:
                companies.append(
                    CorpCode(corp_code=corp_code, corp_name=corp_name, stock_code=stock_code)
                )
        return companies

    async def list_disclosures(self, bgn_de: str, end_de: str) -> list[Disclosure]:
        """기간(YYYYMMDD) 내 전체 공시 목록을 조회한다 (페이지 자동 순회)."""
        disclosures: list[Disclosure] = []
        for page_no in range(1, MAX_PAGES + 1):
            response = await self._http.get(
                f"{BASE_URL}/list.json",
                params={
                    "crtfc_key": self._api_key,
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "page_no": page_no,
                    "page_count": 100,
                },
            )
            response.raise_for_status()
            payload = response.json()

            status = str(payload.get("status", ""))
            if status in NO_DATA_CODES:
                break
            if status not in SUCCESS_CODES:
                raise DartError(
                    f"DART 오류 {status}: {payload.get('message', '알 수 없는 오류')}"
                )

            rows = payload.get("list", [])
            disclosures.extend(_parse_disclosure(row) for row in rows)

            total_page = int(payload.get("total_page", 1))
            if page_no >= total_page or not rows:
                break
        return disclosures


def _parse_disclosure(row: dict) -> Disclosure:
    return Disclosure(
        rcept_no=str(row.get("rcept_no", "")).strip(),
        corp_code=str(row.get("corp_code", "")).strip(),
        corp_name=str(row.get("corp_name", "")).strip(),
        report_nm=str(row.get("report_nm", "")).strip(),
        rcept_dt=str(row.get("rcept_dt", "")).strip(),
        flr_nm=str(row.get("flr_nm", "")).strip(),
    )
