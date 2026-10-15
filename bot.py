"""dart-alert-bot 엔트리포인트.

DART 전자공시를 5분마다 확인해 관심기업·키워드 공시를 알려주는 24/7 텔레그램 봇.
"""

from __future__ import annotations

import logging
from datetime import time as dtime

import httpx
from dotenv import load_dotenv
from telegram import BotCommand, Update

from app.bot import build_application
from app.clients.dart import DartClient, DartError
from app.config import Config
from app.handlers import dart
from app.services.repository import Repository

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS companies (
      corp_code TEXT PRIMARY KEY,
      corp_name TEXT NOT NULL,
      stock_code TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      chat_id INTEGER NOT NULL,
      corp_code TEXT NOT NULL,
      corp_name TEXT NOT NULL,
      UNIQUE (chat_id, corp_code)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS keywords (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      chat_id INTEGER NOT NULL,
      keyword TEXT NOT NULL,
      UNIQUE (chat_id, keyword)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS disclosures (
      rcept_no TEXT PRIMARY KEY,
      corp_code TEXT NOT NULL,
      corp_name TEXT NOT NULL,
      report_nm TEXT NOT NULL,
      rcept_dt TEXT NOT NULL,
      flr_nm TEXT,
      fetched_at TEXT NOT NULL,
      processed_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
      chat_id INTEGER PRIMARY KEY,
      morning INTEGER NOT NULL DEFAULT 0,
      last_morning_date TEXT
    );
    """,
]

COMMANDS = [
    BotCommand("add", "관심기업 등록"),
    BotCommand("list", "관심기업 목록"),
    BotCommand("rms", "관심기업 삭제"),
    BotCommand("keyword", "키워드 알림 등록"),
    BotCommand("keywords", "키워드 목록"),
    BotCommand("del", "키워드 삭제"),
    BotCommand("latest", "최근 공시 5건"),
    BotCommand("morning", "아침 요약 켜기/끄기"),
    BotCommand("settings", "내 설정 요약"),
    BotCommand("start", "시작"),
    BotCommand("help", "명령어 목록"),
    BotCommand("status", "봇 상태"),
    BotCommand("id", "내 chat id"),
]

POLL_INTERVAL_SECONDS = 300
MORNING_TIME = dtime(hour=8, minute=30)


async def setup(application) -> None:
    config: Config = application.bot_data["config"]
    http = httpx.AsyncClient(timeout=30.0)
    application.bot_data["http"] = http
    client = DartClient(http, config.dart_api_key)
    application.bot_data["dart"] = client
    repo = Repository(application.bot_data["db"])
    application.bot_data["repo"] = repo

    if await repo.count_companies() == 0:
        try:
            companies = await client.fetch_corp_codes()
            await repo.bulk_insert_companies(companies)
            logging.getLogger(__name__).info("기업 코드 %d건 캐시 완료", len(companies))
        except (DartError, httpx.HTTPError):
            logging.getLogger(__name__).warning(
                "기업 코드 다운로드 실패 — 다음 시작 시 재시도합니다", exc_info=True
            )


async def teardown(application) -> None:
    http: httpx.AsyncClient | None = application.bot_data.get("http")
    if http is not None:
        await http.aclose()


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    application = build_application(
        config,
        migrations=MIGRATIONS,
        extra_handlers=dart.handlers(),
        help_text=dart.DART_HELP,
        commands=COMMANDS,
        setup=setup,
        teardown=teardown,
    )
    application.job_queue.run_repeating(
        dart.poll_job, interval=POLL_INTERVAL_SECONDS, first=30, name="poll"
    )
    application.job_queue.run_daily(
        dart.morning_job, time=MORNING_TIME.replace(tzinfo=dart.KST), name="morning"
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
