"""공시 메시지 포맷 (순수 함수)."""

from __future__ import annotations

from datetime import datetime

from app.services.repository import DisclosureRecord
from app.utils.text import chunk_text


def format_date(ymd: str) -> str:
    """'20261015' → '10/15'. 형식이 다르면 원문."""
    try:
        parsed = datetime.strptime(ymd, "%Y%m%d")
    except ValueError:
        return ymd
    return f"{parsed.month}/{parsed.day}"


def format_disclosure(disclosure: DisclosureRecord) -> str:
    lines = [
        f"[공시] {disclosure.corp_name}",
        disclosure.report_nm,
    ]
    meta = f"접수 {format_date(disclosure.rcept_dt)}"
    if disclosure.flr_nm and disclosure.flr_nm != disclosure.corp_name:
        meta += f" · 제출 {disclosure.flr_nm}"
    lines.append(meta)
    lines.append(disclosure.url)
    return "\n".join(lines)


def format_morning(date_label: str, disclosures: list[DisclosureRecord]) -> list[str]:
    lines = [f"어제({date_label}) 관심기업 공시 {len(disclosures)}건"]
    for disclosure in disclosures:
        lines.append(f"· {disclosure.corp_name} — {disclosure.report_nm}")
        lines.append(f"  {disclosure.url}")
    return chunk_text("\n".join(lines))
