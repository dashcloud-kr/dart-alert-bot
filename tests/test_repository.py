"""Repository (기업·관심기업·키워드·공시·설정) 테스트."""

from __future__ import annotations

from app.clients.dart import CorpCode
from app.services.repository import DisclosureRecord


def make_company(code: str = "00126380", name: str = "삼성전자", stock: str = "005930") -> CorpCode:
    return CorpCode(corp_code=code, corp_name=name, stock_code=stock)


def make_record(
    rcept_no: str = "R1", corp_code: str = "00126380", dt: str = "20261015"
) -> DisclosureRecord:
    return DisclosureRecord(
        rcept_no=rcept_no,
        corp_code=corp_code,
        corp_name="삼성전자",
        report_nm="주요사항보고서(자기주식취득결정)",
        rcept_dt=dt,
        flr_nm="삼성전자",
    )


async def test_기업_벌크삽입과_검색(repo):
    assert await repo.count_companies() == 0
    await repo.bulk_insert_companies(
        [
            make_company(),
            make_company("00164779", "삼성물산", "028260"),
            make_company("X", "삼성SDI"),
        ]
    )
    await repo.bulk_insert_companies([make_company()])  # 중복 무시
    assert await repo.count_companies() == 3

    exact = await repo.find_companies("삼성전자")
    assert [c.corp_name for c in exact] == ["삼성전자"]

    partial = await repo.find_companies("삼성")
    assert len(partial) == 3  # 이름 길이 순

    none = await repo.find_companies("없는회사")
    assert none == []


async def test_관심기업_등록_중복_삭제(repo):
    assert await repo.add_watch(1, 100, make_company()) is True
    assert await repo.add_watch(1, 100, make_company()) is False
    assert await repo.add_watch(1, 200, make_company()) is True

    entries = await repo.list_watch(100)
    assert len(entries) == 1
    assert entries[0].corp_name == "삼성전자"
    assert await repo.count_watch(100) == 1

    assert await repo.remove_watch(100, entries[0].id) is True
    assert await repo.remove_watch(100, entries[0].id) is False

    rows = await repo.all_watch_rows()
    assert rows == [(200, "00126380", "삼성전자")]


async def test_키워드(repo):
    assert await repo.add_keyword(1, 100, "유상증자") is True
    assert await repo.add_keyword(1, 100, "유상증자") is False
    assert await repo.list_keywords(100) == ["유상증자"]
    assert await repo.remove_keyword(100, "유상증자") is True
    assert await repo.remove_keyword(100, "유상증자") is False
    assert await repo.all_keyword_rows() == []


async def test_공시_삽입_중복_미처리(repo):
    assert await repo.insert_disclosure(make_record("R1"), "2026-10-15T09:00:00+09:00") is True
    assert await repo.insert_disclosure(make_record("R1"), "2026-10-15T09:01:00+09:00") is False
    assert await repo.count_disclosures() == 1

    unprocessed = await repo.unprocessed_disclosures()
    assert [d.rcept_no for d in unprocessed] == ["R1"]

    await repo.mark_processed(["R1"], "2026-10-15T09:02:00+09:00")
    assert await repo.unprocessed_disclosures() == []

    recent = await repo.recent_disclosures()
    assert recent[0].rcept_no == "R1"
    assert recent[0].url.endswith("rcpNo=R1")


async def test_기간_조회(repo):
    await repo.insert_disclosure(make_record("R1", dt="20261014"), "t")
    await repo.insert_disclosure(make_record("R2", dt="20261015"), "t")
    between = await repo.disclosures_between("20261014", "20261014")
    assert [d.rcept_no for d in between] == ["R1"]


async def test_아침_설정(repo):
    assert (await repo.get_morning(100)).morning is False
    await repo.set_morning(100, True)
    assert (await repo.get_morning(100)).morning is True
    assert await repo.morning_chats() == [100]

    await repo.mark_morning_sent(100, "20261014")
    assert (await repo.get_morning(100)).last_morning_date == "20261014"

    await repo.set_morning(100, False)
    assert await repo.morning_chats() == []


async def test_마이그레이션_재적용_안전(tmp_path):
    from app.db import Database
    from app.services.repository import Repository
    from bot import MIGRATIONS

    path = tmp_path / "again.db"
    first = Database(path)
    await first.connect(MIGRATIONS)
    await Repository(first).bulk_insert_companies([make_company()])
    await first.close()

    second = Database(path)
    await second.connect(MIGRATIONS)
    try:
        assert await Repository(second).count_companies() == 1
    finally:
        await second.close()
