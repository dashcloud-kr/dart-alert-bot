"""SQLite 저장소 (기업 캐시·관심기업·키워드·공시·설정)."""

from __future__ import annotations

from dataclasses import dataclass

from app.clients.dart import CorpCode
from app.db import Database


@dataclass(frozen=True)
class CorpEntry:
    id: int
    corp_code: str
    corp_name: str
    stock_code: str


@dataclass(frozen=True)
class DisclosureRecord:
    rcept_no: str
    corp_code: str
    corp_name: str
    report_nm: str
    rcept_dt: str
    flr_nm: str

    @property
    def url(self) -> str:
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"


@dataclass(frozen=True)
class MorningSetting:
    chat_id: int
    morning: bool
    last_morning_date: str | None


def _row_to_disclosure(row) -> DisclosureRecord:
    return DisclosureRecord(
        rcept_no=str(row["rcept_no"]),
        corp_code=str(row["corp_code"]),
        corp_name=str(row["corp_name"]),
        report_nm=str(row["report_nm"]),
        rcept_dt=str(row["rcept_dt"]),
        flr_nm=str(row["flr_nm"] or ""),
    )


class Repository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- 기업 코드 캐시 ---------------------------------------------------

    async def count_companies(self) -> int:
        row = await self._db.fetchone("SELECT COUNT(*) AS count FROM companies")
        return int(row["count"]) if row is not None else 0

    async def bulk_insert_companies(self, companies: list[CorpCode]) -> None:
        await self._db.executemany(
            "INSERT OR IGNORE INTO companies (corp_code, corp_name, stock_code) VALUES (?, ?, ?)",
            [(c.corp_code, c.corp_name, c.stock_code) for c in companies],
        )

    async def find_companies(self, query: str, limit: int = 5) -> list[CorpCode]:
        """정확 일치 우선, 그다음 이름 포함 검색."""
        rows = await self._db.fetchall(
            "SELECT corp_code, corp_name, stock_code FROM companies "
            "WHERE corp_name = ? LIMIT ?",
            (query, limit),
        )
        if not rows:
            rows = await self._db.fetchall(
                "SELECT corp_code, corp_name, stock_code FROM companies "
                "WHERE corp_name LIKE ? ORDER BY LENGTH(corp_name) LIMIT ?",
                (f"%{query}%", limit),
            )
        return [
            CorpCode(
                corp_code=str(row["corp_code"]),
                corp_name=str(row["corp_name"]),
                stock_code=str(row["stock_code"] or ""),
            )
            for row in rows
        ]

    # ---- 관심기업 ---------------------------------------------------------

    async def add_watch(self, user_id: int, chat_id: int, company: CorpCode) -> bool:
        affected = await self._db.execute_affected(
            "INSERT OR IGNORE INTO watchlist (user_id, chat_id, corp_code, corp_name) "
            "VALUES (?, ?, ?, ?)",
            (user_id, chat_id, company.corp_code, company.corp_name),
        )
        return affected > 0

    async def list_watch(self, chat_id: int) -> list[CorpEntry]:
        rows = await self._db.fetchall(
            "SELECT id, corp_code, corp_name FROM watchlist WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        )
        return [
            CorpEntry(
                id=int(row["id"]),
                corp_code=str(row["corp_code"]),
                corp_name=str(row["corp_name"]),
                stock_code="",
            )
            for row in rows
        ]

    async def remove_watch(self, chat_id: int, entry_id: int) -> bool:
        affected = await self._db.execute_affected(
            "DELETE FROM watchlist WHERE chat_id = ? AND id = ?", (chat_id, entry_id)
        )
        return affected > 0

    async def count_watch(self, chat_id: int) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) AS count FROM watchlist WHERE chat_id = ?", (chat_id,)
        )
        return int(row["count"]) if row is not None else 0

    async def all_watch_rows(self) -> list[tuple[int, str, str]]:
        """(chat_id, corp_code, corp_name) 전체 — 폴링용."""
        rows = await self._db.fetchall("SELECT chat_id, corp_code, corp_name FROM watchlist")
        return [
            (int(row["chat_id"]), str(row["corp_code"]), str(row["corp_name"]))
            for row in rows
        ]

    # ---- 키워드 -----------------------------------------------------------

    async def add_keyword(self, user_id: int, chat_id: int, keyword: str) -> bool:
        affected = await self._db.execute_affected(
            "INSERT OR IGNORE INTO keywords (user_id, chat_id, keyword) VALUES (?, ?, ?)",
            (user_id, chat_id, keyword),
        )
        return affected > 0

    async def list_keywords(self, chat_id: int) -> list[str]:
        rows = await self._db.fetchall(
            "SELECT keyword FROM keywords WHERE chat_id = ? ORDER BY id", (chat_id,)
        )
        return [str(row["keyword"]) for row in rows]

    async def remove_keyword(self, chat_id: int, keyword: str) -> bool:
        affected = await self._db.execute_affected(
            "DELETE FROM keywords WHERE chat_id = ? AND keyword = ?", (chat_id, keyword)
        )
        return affected > 0

    async def all_keyword_rows(self) -> list[tuple[int, str]]:
        rows = await self._db.fetchall("SELECT chat_id, keyword FROM keywords")
        return [(int(row["chat_id"]), str(row["keyword"])) for row in rows]

    # ---- 공시 -------------------------------------------------------------

    async def insert_disclosure(self, disclosure: DisclosureRecord, fetched_at: str) -> bool:
        affected = await self._db.execute_affected(
            "INSERT OR IGNORE INTO disclosures "
            "(rcept_no, corp_code, corp_name, report_nm, rcept_dt, flr_nm, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                disclosure.rcept_no,
                disclosure.corp_code,
                disclosure.corp_name,
                disclosure.report_nm,
                disclosure.rcept_dt,
                disclosure.flr_nm,
                fetched_at,
            ),
        )
        return affected > 0

    async def count_disclosures(self) -> int:
        row = await self._db.fetchone("SELECT COUNT(*) AS count FROM disclosures")
        return int(row["count"]) if row is not None else 0

    async def unprocessed_disclosures(self, limit: int = 500) -> list[DisclosureRecord]:
        rows = await self._db.fetchall(
            "SELECT rcept_no, corp_code, corp_name, report_nm, rcept_dt, flr_nm "
            "FROM disclosures WHERE processed_at IS NULL ORDER BY rcept_dt, rcept_no LIMIT ?",
            (limit,),
        )
        return [_row_to_disclosure(row) for row in rows]

    async def mark_processed(self, rcept_nos: list[str], at_iso: str) -> None:
        for rcept_no in rcept_nos:
            await self._db.execute(
                "UPDATE disclosures SET processed_at = ? WHERE rcept_no = ?",
                (at_iso, rcept_no),
            )

    async def recent_disclosures(self, limit: int = 5) -> list[DisclosureRecord]:
        rows = await self._db.fetchall(
            "SELECT rcept_no, corp_code, corp_name, report_nm, rcept_dt, flr_nm "
            "FROM disclosures ORDER BY rowid DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_disclosure(row) for row in rows]

    async def disclosures_between(self, bgn_de: str, end_de: str) -> list[DisclosureRecord]:
        rows = await self._db.fetchall(
            "SELECT rcept_no, corp_code, corp_name, report_nm, rcept_dt, flr_nm "
            "FROM disclosures WHERE rcept_dt BETWEEN ? AND ? ORDER BY rcept_dt",
            (bgn_de, end_de),
        )
        return [_row_to_disclosure(row) for row in rows]

    # ---- 설정 -------------------------------------------------------------

    async def set_morning(self, chat_id: int, enabled: bool) -> None:
        await self._db.execute(
            "INSERT INTO settings (chat_id, morning) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET morning = excluded.morning",
            (chat_id, 1 if enabled else 0),
        )

    async def get_morning(self, chat_id: int) -> MorningSetting:
        row = await self._db.fetchone(
            "SELECT chat_id, morning, last_morning_date FROM settings WHERE chat_id = ?",
            (chat_id,),
        )
        if row is None:
            return MorningSetting(chat_id=chat_id, morning=False, last_morning_date=None)
        return MorningSetting(
            chat_id=int(row["chat_id"]),
            morning=bool(row["morning"]),
            last_morning_date=(
                str(row["last_morning_date"]) if row["last_morning_date"] is not None else None
            ),
        )

    async def morning_chats(self) -> list[int]:
        rows = await self._db.fetchall("SELECT chat_id FROM settings WHERE morning = 1")
        return [int(row["chat_id"]) for row in rows]

    async def mark_morning_sent(self, chat_id: int, ymd: str) -> None:
        await self._db.execute(
            "UPDATE settings SET last_morning_date = ? WHERE chat_id = ?", (ymd, chat_id)
        )
