"""공시 명령어와 백그라운드 잡."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.clients.dart import CorpCode, DartClient, DartError
from app.services.formatting import format_date, format_disclosure, format_morning
from app.services.repository import Repository

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

WATCH_LIMIT = 20
KEYWORD_LIMIT = 10
LATEST_COUNT = 5
SEARCH_RESULTS_KEY = "dart_company_results"

DART_HELP = """공시 알림 봇 — 명령어 목록

/add 삼성전자 — 관심기업 등록 (최대 20개)
/list — 관심기업 목록
/rms 3 — 관심기업 삭제

/keyword 유상증자 — 키워드 알림 (모든 기업 대상, 최대 10개)
/keywords — 키워드 목록
/del 유상증자 — 키워드 삭제

/latest — 최근 공시 5건
/morning on — 매일 08:30 어제 관심기업 공시 요약
/settings — 내 설정 요약

/status — 봇 상태 · /id — 내 chat id

출처: DART 전자공시 (5분마다 확인)"""


def handlers() -> list[CommandHandler | CallbackQueryHandler]:
    return [
        CommandHandler("add", cmd_add),
        CommandHandler("list", cmd_list),
        CommandHandler("rms", cmd_rms),
        CommandHandler("keyword", cmd_keyword),
        CommandHandler("keywords", cmd_keywords),
        CommandHandler("del", cmd_del),
        CommandHandler("latest", cmd_latest),
        CommandHandler("morning", cmd_morning),
        CommandHandler("settings", cmd_settings),
        CallbackQueryHandler(on_register_callback, pattern=r"^reg:\d+$"),
    ]


# ---- 내부 헬퍼 -------------------------------------------------------------


def _repo(context: ContextTypes.DEFAULT_TYPE) -> Repository:
    return context.bot_data["repo"]


def _dart(context: ContextTypes.DEFAULT_TYPE) -> DartClient:
    return context.bot_data["dart"]


def _ids(update: Update) -> tuple[int, int] | None:
    if update.effective_user is None or update.effective_chat is None:
        return None
    return update.effective_user.id, update.effective_chat.id


async def _say(update: Update, text: str) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text(text)


async def _notify(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except TelegramError:
        logger.warning("알림 전송 실패 (chat_id=%s)", chat_id, exc_info=True)


# ---- 명령어 ----------------------------------------------------------------


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await _say(update, "사용법: /add 삼성전자")
        return
    query = " ".join(context.args)
    companies = await _repo(context).find_companies(query)
    if not companies:
        await _say(
            update,
            f"'{query}' 검색 결과가 없습니다. 정식 명칭으로 다시 시도해보세요. (예: 삼성전자)",
        )
        return

    context.user_data[SEARCH_RESULTS_KEY] = companies
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{company.corp_name}"
                    + (f" ({company.stock_code})" if company.stock_code else " (비상장)"),
                    callback_data=f"reg:{index}",
                )
            ]
            for index, company in enumerate(companies)
        ]
    )
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "검색 결과 — 등록할 기업을 선택하세요 (최대 20개)",
            reply_markup=keyboard,
        )


async def on_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    companies: list[CorpCode] = context.user_data.get(SEARCH_RESULTS_KEY) or []
    index_text = (query.data or "").removeprefix("reg:")
    if not index_text.isdigit() or int(index_text) >= len(companies):
        await _notify_chat(context, query, "검색 결과가 만료됐습니다. /add 로 다시 검색해주세요.")
        return

    company = companies[int(index_text)]
    chat = query.message.chat if query.message is not None else None
    if chat is None:
        return

    repo = _repo(context)
    if await repo.count_watch(chat.id) >= WATCH_LIMIT:
        await _notify_chat(
            context, query, f"관심기업은 최대 {WATCH_LIMIT}개까지 등록할 수 있습니다."
        )
        return

    user = query.from_user
    if await repo.add_watch(user.id, chat.id, company):
        await _notify_chat(
            context,
            query,
            f"등록 완료: {company.corp_name}\n새 공시가 올라오면 바로 알려드립니다.",
        )
    else:
        await _notify_chat(context, query, f"{company.corp_name}은(는) 이미 등록되어 있습니다.")


async def _notify_chat(context: ContextTypes.DEFAULT_TYPE, query, text: str) -> None:
    chat = query.message.chat if query.message is not None else None
    if chat is None:
        return
    try:
        await context.bot.send_message(chat_id=chat.id, text=text)
    except TelegramError:
        logger.warning("메시지 전송 실패", exc_info=True)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    _user_id, chat_id = ids
    entries = await _repo(context).list_watch(chat_id)
    if not entries:
        await _say(update, "등록된 관심기업이 없습니다. /add 삼성전자 로 검색해보세요.")
        return
    lines = ["관심기업"]
    for entry in entries:
        lines.append(f"#{entry.id} {entry.corp_name}")
    await _say(update, "\n".join(lines))


async def cmd_rms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    _user_id, chat_id = ids
    if not context.args or not context.args[0].isdigit():
        await _say(update, "사용법: /rms 3 (/list 에서 번호 확인)")
        return
    removed = await _repo(context).remove_watch(chat_id, int(context.args[0]))
    await _say(update, "삭제했습니다." if removed else "해당 번호의 기업이 없습니다.")


async def cmd_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    user_id, chat_id = ids
    if not context.args:
        await _say(update, "사용법: /keyword 유상증자 (공시명에 포함되면 알림)")
        return
    keyword = " ".join(context.args)
    repo = _repo(context)
    current = await repo.list_keywords(chat_id)
    if keyword not in current and len(current) >= KEYWORD_LIMIT:
        await _say(update, f"키워드는 최대 {KEYWORD_LIMIT}개까지 등록할 수 있습니다.")
        return
    added = await repo.add_keyword(user_id, chat_id, keyword)
    await _say(
        update,
        f"키워드 추가: {keyword}" if added else f"'{keyword}'는 이미 등록되어 있습니다.",
    )


async def cmd_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    _user_id, chat_id = ids
    keywords = await _repo(context).list_keywords(chat_id)
    if not keywords:
        await _say(update, "등록된 키워드가 없습니다. /keyword 유상증자")
        return
    await _say(update, f"키워드 ({len(keywords)}/{KEYWORD_LIMIT}): " + ", ".join(keywords))


async def cmd_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    _user_id, chat_id = ids
    if not context.args:
        await _say(update, "사용법: /del 유상증자")
        return
    keyword = " ".join(context.args)
    removed = await _repo(context).remove_keyword(chat_id, keyword)
    message = f"'{keyword}' 삭제했습니다." if removed else f"'{keyword}' 키워드가 없습니다."
    await _say(update, message)


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    disclosures = await _repo(context).recent_disclosures(LATEST_COUNT)
    if not disclosures:
        await _say(update, "아직 수집된 공시가 없습니다. 잠시 후 다시 시도하세요.")
        return
    await _say(update, f"최근 공시 {len(disclosures)}건")
    for disclosure in disclosures:
        await _say(update, format_disclosure(disclosure))


async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    _user_id, chat_id = ids
    repo = _repo(context)
    if not context.args or context.args[0].lower() not in {"on", "off", "켜기", "끄기"}:
        setting = await repo.get_morning(chat_id)
        state = "켜짐" if setting.morning else "꺼짐"
        await _say(update, f"아침 요약: {state}\n사용법: /morning on 또는 /morning off")
        return
    enabled = context.args[0].lower() in {"on", "켜기"}
    await repo.set_morning(chat_id, enabled)
    if enabled:
        await _say(
            update,
            "아침 요약을 켰습니다. 매일 08:30 (KST)에 어제 관심기업 공시를 정리해드립니다.",
        )
    else:
        await _say(update, "아침 요약을 껐습니다.")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ids = _ids(update)
    if ids is None:
        return
    _user_id, chat_id = ids
    repo = _repo(context)
    entries = await repo.list_watch(chat_id)
    keywords = await repo.list_keywords(chat_id)
    setting = await repo.get_morning(chat_id)
    lines = [
        "내 설정",
        f"관심기업 ({len(entries)}/{WATCH_LIMIT}): "
        + (", ".join(e.corp_name for e in entries) if entries else "없음"),
        f"키워드 ({len(keywords)}/{KEYWORD_LIMIT}): "
        + (", ".join(keywords) if keywords else "없음"),
        f"아침 요약: {'켜짐' if setting.morning else '꺼짐'}",
    ]
    await _say(update, "\n".join(lines))


# ---- 백그라운드 잡 ---------------------------------------------------------


async def poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """5분마다 오늘의 공시를 수집해 관심기업·키워드에 맞는 알림을 보낸다."""
    repo = _repo(context)
    client = _dart(context)

    today = datetime.now(KST).strftime("%Y%m%d")
    bootstrap = await repo.count_disclosures() == 0

    try:
        disclosures = await client.list_disclosures(today, today)
    except DartError:
        logger.warning("DART 오류", exc_info=True)
        return
    except httpx.HTTPError:
        logger.warning("DART 통신 실패", exc_info=True)
        return

    if not disclosures:
        return

    fetched_at = datetime.now(KST).isoformat()
    if bootstrap:
        # 첫 실행: 기존 공시는 알림 없이 등록만
        for disclosure in disclosures:
            await repo.insert_disclosure(disclosure, fetched_at)
        await repo.mark_processed([d.rcept_no for d in disclosures], fetched_at)
        logger.info("부트스트랩: 공시 %d건 등록 (알림 없음)", len(disclosures))
        return

    for disclosure in disclosures:
        await repo.insert_disclosure(disclosure, fetched_at)

    unprocessed = await repo.unprocessed_disclosures()
    if not unprocessed:
        return

    watch_rows = await repo.all_watch_rows()
    keyword_rows = await repo.all_keyword_rows()

    watch_by_chat: dict[int, set[str]] = defaultdict(set)
    for chat_id, corp_code, _corp_name in watch_rows:
        watch_by_chat[chat_id].add(corp_code)

    for disclosure in unprocessed:
        targets: set[int] = {
            chat_id
            for chat_id, codes in watch_by_chat.items()
            if disclosure.corp_code in codes
        }
        report_lower = disclosure.report_nm.lower()
        for chat_id, keyword in keyword_rows:
            if keyword.lower() in report_lower:
                targets.add(chat_id)

        for chat_id in targets:
            await _notify(context, chat_id, format_disclosure(disclosure))
        await repo.mark_processed([disclosure.rcept_no], fetched_at)


async def morning_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """매일 08:30 (KST) 어제 관심기업 공시를 요약해 보낸다."""
    repo = _repo(context)
    chats = await repo.morning_chats()
    if not chats:
        return

    yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y%m%d")
    disclosures = await repo.disclosures_between(yesterday, yesterday)
    if not disclosures:
        return

    watch_by_chat: dict[int, set[str]] = defaultdict(set)
    for chat_id, corp_code, _corp_name in await repo.all_watch_rows():
        watch_by_chat[chat_id].add(corp_code)

    for chat_id in chats:
        codes = watch_by_chat.get(chat_id, set())
        if not codes:
            continue
        mine = [d for d in disclosures if d.corp_code in codes]
        if not mine:
            continue
        for chunk in format_morning(format_date(yesterday), mine):
            await _notify(context, chat_id, chunk)
        await repo.mark_morning_sent(chat_id, yesterday)
