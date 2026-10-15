"""PTB Update/Context 테스트 팩토리."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telegram import Bot, Update


def make_bot() -> MagicMock:
    """네트워크 호출 없이 전송을 기록하는 가짜 Bot."""
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.answer_callback_query = AsyncMock()
    return bot


def _message_payload(
    text: str,
    *,
    user_id: int,
    chat_id: int,
    chat_type: str,
    first_name: str,
    message_id: int = 1,
) -> dict:
    return {
        "message_id": message_id,
        "date": int(datetime.now(UTC).timestamp()),
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": user_id, "is_bot": False, "first_name": first_name},
        "text": text,
    }


def make_message_update(
    text: str = "/start",
    *,
    user_id: int = 100,
    chat_id: int = 100,
    chat_type: str = "private",
    first_name: str = "테스터",
    update_id: int = 1,
) -> Update:
    data = {
        "update_id": update_id,
        "message": _message_payload(
            text,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            first_name=first_name,
        ),
    }
    update = Update.de_json(data, bot=make_bot())
    assert update is not None
    return update


def make_callback_update(
    data: str,
    *,
    user_id: int = 100,
    chat_id: int = 100,
    update_id: int = 2,
) -> Update:
    payload = {
        "update_id": update_id,
        "callback_query": {
            "id": "cb-1",
            "from": {"id": user_id, "is_bot": False, "first_name": "테스터"},
            "chat_instance": "ci-1",
            "data": data,
            "message": _message_payload(
                "검색 결과",
                user_id=999,
                chat_id=chat_id,
                chat_type="private",
                first_name="bot",
            ),
        },
    }
    update = Update.de_json(payload, bot=make_bot())
    assert update is not None
    return update


def make_context(
    *,
    args: list[str] | None = None,
    bot_data: dict | None = None,
    error: BaseException | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        bot=make_bot(),
        args=args or [],
        bot_data=bot_data or {},
        user_data={},
        chat_data={},
        error=error,
    )
