"""공시 명령어 핸들러 테스트."""

from __future__ import annotations

from app.clients.dart import CorpCode
from app.handlers import dart
from tests.factories import make_callback_update, make_context, make_message_update
from tests.test_repository import make_company


def _ctx(update, repo):
    message = update.effective_message
    args = message.text.split()[1:] if message is not None and message.text else []
    return make_context(args=args, bot_data={"repo": repo})


def _ctx_texts(ctx) -> list[str]:
    return [call.kwargs["text"] for call in ctx.bot.send_message.await_args_list]


def _last(update) -> str:
    texts = [call.kwargs["text"] for call in update.get_bot().send_message.await_args_list]
    return texts[-1]


# ---- /add + 콜백 ------------------------------------------------------------


async def test_add_사용법과_결과없음(repo):
    update = make_message_update("/add")
    await dart.cmd_add(update, _ctx(update, repo))
    assert "사용법" in _last(update)

    update = make_message_update("/add 없는회사")
    await dart.cmd_add(update, _ctx(update, repo))
    assert "검색 결과가 없습니다" in _last(update)


async def test_add_검색과_등록(repo):
    await repo.bulk_insert_companies([make_company()])
    update = make_message_update("/add 삼성전자")
    ctx = _ctx(update, repo)
    await dart.cmd_add(update, ctx)

    call = update.get_bot().send_message.await_args
    assert "검색 결과" in call.kwargs["text"]
    assert call.kwargs["reply_markup"] is not None

    callback = make_callback_update("reg:0")
    await dart.on_register_callback(callback, ctx)

    entries = await repo.list_watch(100)
    assert len(entries) == 1
    assert entries[0].corp_name == "삼성전자"
    assert any("등록 완료" in text for text in _ctx_texts(ctx))


async def test_add_콜백_만료와_중복(repo):
    ctx = make_context(bot_data={"repo": repo})
    callback = make_callback_update("reg:0")
    await dart.on_register_callback(callback, ctx)
    assert any("만료" in text for text in _ctx_texts(ctx))

    # 정상 등록 후 중복 클릭
    await repo.bulk_insert_companies([make_company()])
    update = make_message_update("/add 삼성전자")
    ctx = _ctx(update, repo)
    await dart.cmd_add(update, ctx)
    await dart.on_register_callback(callback, ctx)
    await dart.on_register_callback(callback, ctx)
    assert any("이미 등록" in text for text in _ctx_texts(ctx))


async def test_add_한도(repo):
    await repo.bulk_insert_companies([make_company()])
    for i in range(20):
        await repo.add_watch(100, 100, make_company(f"C{i}", f"회사{i}"))
    update = make_message_update("/add 삼성전자")
    ctx = _ctx(update, repo)
    await dart.cmd_add(update, ctx)
    await dart.on_register_callback(make_callback_update("reg:0"), ctx)
    assert any("최대 20개" in text for text in _ctx_texts(ctx))


# ---- /list, /rms ------------------------------------------------------------


async def test_list과_rms(repo):
    update = make_message_update("/list")
    await dart.cmd_list(update, _ctx(update, repo))
    assert "관심기업이 없습니다" in _last(update)

    await repo.add_watch(100, 100, make_company())
    update = make_message_update("/list")
    await dart.cmd_list(update, _ctx(update, repo))
    assert "삼성전자" in _last(update)

    entries = await repo.list_watch(100)
    update = make_message_update(f"/rms {entries[0].id}")
    await dart.cmd_rms(update, _ctx(update, repo))
    assert "삭제했습니다" in _last(update)

    update = make_message_update("/rms abc")
    await dart.cmd_rms(update, _ctx(update, repo))
    assert "사용법" in _last(update)


# ---- /keyword, /keywords, /del ----------------------------------------------


async def test_keyword_추가_목록_삭제(repo):
    update = make_message_update("/keyword")
    await dart.cmd_keyword(update, _ctx(update, repo))
    assert "사용법" in _last(update)

    update = make_message_update("/keyword 유상증자")
    await dart.cmd_keyword(update, _ctx(update, repo))
    assert "키워드 추가" in _last(update)

    update = make_message_update("/keyword 유상증자")
    await dart.cmd_keyword(update, _ctx(update, repo))
    assert "이미 등록" in _last(update)

    update = make_message_update("/keywords")
    await dart.cmd_keywords(update, _ctx(update, repo))
    assert "유상증자" in _last(update)

    update = make_message_update("/del 유상증자")
    await dart.cmd_del(update, _ctx(update, repo))
    assert "삭제했습니다" in _last(update)


async def test_keyword_한도(repo):
    for i in range(10):
        await repo.add_keyword(100, 100, f"kw{i}")
    update = make_message_update("/keyword 새키워드")
    await dart.cmd_keyword(update, _ctx(update, repo))
    assert "최대 10개" in _last(update)


# ---- /latest, /morning, /settings -------------------------------------------


async def test_latest(repo):
    update = make_message_update("/latest")
    await dart.cmd_latest(update, _ctx(update, repo))
    assert "없습니다" in _last(update)

    from tests.test_repository import make_record

    await repo.insert_disclosure(make_record("R1"), "t")
    update = make_message_update("/latest")
    await dart.cmd_latest(update, _ctx(update, repo))
    texts = [call.kwargs["text"] for call in update.get_bot().send_message.await_args_list]
    assert "최근 공시 1건" in texts[0]
    assert "[공시] 삼성전자" in texts[1]


async def test_morning_설정(repo):
    update = make_message_update("/morning")
    await dart.cmd_morning(update, _ctx(update, repo))
    assert "꺼짐" in _last(update)

    update = make_message_update("/morning on")
    await dart.cmd_morning(update, _ctx(update, repo))
    assert "켰습니다" in _last(update)
    assert (await repo.get_morning(100)).morning is True

    update = make_message_update("/morning off")
    await dart.cmd_morning(update, _ctx(update, repo))
    assert (await repo.get_morning(100)).morning is False


async def test_settings_요약(repo):
    await repo.add_watch(100, 100, make_company())
    await repo.add_keyword(100, 100, "유상증자")
    await repo.set_morning(100, True)

    update = make_message_update("/settings")
    await dart.cmd_settings(update, _ctx(update, repo))
    text = _last(update)
    assert "삼성전자" in text
    assert "유상증자" in text
    assert "켜짐" in text


def test_CorpCode_타입_사용():
    company = CorpCode(corp_code="1", corp_name="A", stock_code="")
    assert company.stock_code == ""
