"""폴링·아침 요약 잡 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.clients.dart import DartError
from app.handlers import dart
from tests.factories import make_context
from tests.test_repository import make_company, make_record


class StubDart:
    def __init__(self, disclosures=None) -> None:
        self._disclosures = disclosures or []
        self.calls: list[tuple[str, str]] = []

    async def list_disclosures(self, bgn_de: str, end_de: str):
        self.calls.append((bgn_de, end_de))
        return list(self._disclosures)


class FailingDart:
    async def list_disclosures(self, bgn_de: str, end_de: str):
        raise DartError("020")


def _ctx(repo, client):
    return make_context(bot_data={"repo": repo, "dart": client})


def _texts(ctx) -> list[str]:
    return [call.kwargs["text"] for call in ctx.bot.send_message.await_args_list]


def _today() -> str:
    return datetime.now(dart.KST).strftime("%Y%m%d")


async def test_부트스트랩_기존공시는_알림없이_등록(repo):
    await repo.add_watch(100, 100, make_company())
    client = StubDart([make_record("R1")])
    ctx = _ctx(repo, client)

    await dart.poll_job(ctx)

    assert ctx.bot.send_message.await_count == 0
    assert await repo.count_disclosures() == 1
    assert await repo.unprocessed_disclosures() == []
    assert client.calls[0] == (_today(), _today())


async def test_관심기업_공시_알림(repo):
    await repo.insert_disclosure(make_record("OLD"), "t")
    await repo.mark_processed(["OLD"], "t")
    await repo.add_watch(100, 100, make_company())

    from app.services.repository import DisclosureRecord

    watched = DisclosureRecord(
        rcept_no="R1",
        corp_code="00126380",
        corp_name="삼성전자",
        report_nm="주요사항보고서(자기주식취득결정)",
        rcept_dt="20261015",
        flr_nm="삼성전자",
    )
    other = DisclosureRecord(
        rcept_no="R2",
        corp_code="99999999",
        corp_name="다른회사",
        report_nm="증권신고서",
        rcept_dt="20261015",
        flr_nm="다른회사",
    )
    ctx = _ctx(repo, StubDart([watched, other]))

    await dart.poll_job(ctx)

    assert ctx.bot.send_message.await_count == 1
    assert "[공시] 삼성전자" in _texts(ctx)[0]
    assert await repo.unprocessed_disclosures() == []


async def test_키워드_공시_알림(repo):
    await repo.insert_disclosure(make_record("OLD"), "t")
    await repo.mark_processed(["OLD"], "t")
    await repo.add_keyword(100, 100, "유상증자")

    from app.services.repository import DisclosureRecord

    matched = DisclosureRecord(
        rcept_no="R9",
        corp_code="55555555",
        corp_name="어떤회사",
        report_nm="주요사항보고서(유상증자결정)",
        rcept_dt="20261015",
        flr_nm="어떤회사",
    )
    ctx = _ctx(repo, StubDart([matched]))

    await dart.poll_job(ctx)

    assert ctx.bot.send_message.await_count == 1
    assert "유상증자" in _texts(ctx)[0]


async def test_중복_알림_없음(repo):
    await repo.insert_disclosure(make_record("OLD"), "t")
    await repo.mark_processed(["OLD"], "t")
    await repo.add_watch(100, 100, make_company())

    from app.services.repository import DisclosureRecord

    item = DisclosureRecord(
        rcept_no="R1",
        corp_code="00126380",
        corp_name="삼성전자",
        report_nm="주요사항보고서",
        rcept_dt="20261015",
        flr_nm="삼성전자",
    )
    ctx = _ctx(repo, StubDart([item]))
    await dart.poll_job(ctx)
    assert ctx.bot.send_message.await_count == 1

    await dart.poll_job(ctx)  # 같은 응답 재수집
    assert ctx.bot.send_message.await_count == 1


async def test_구독자_없으면_수집만(repo):
    await repo.insert_disclosure(make_record("OLD"), "t")
    await repo.mark_processed(["OLD"], "t")

    from app.services.repository import DisclosureRecord

    item = DisclosureRecord(
        rcept_no="R1",
        corp_code="00126380",
        corp_name="삼성전자",
        report_nm="주요사항보고서",
        rcept_dt="20261015",
        flr_nm="삼성전자",
    )
    ctx = _ctx(repo, StubDart([item]))
    await dart.poll_job(ctx)

    assert ctx.bot.send_message.await_count == 0
    assert await repo.count_disclosures() == 2
    assert await repo.unprocessed_disclosures() == []


async def test_DART_오류에도_잡은_계속(repo):
    await repo.insert_disclosure(make_record("OLD"), "t")
    await repo.mark_processed(["OLD"], "t")
    ctx = _ctx(repo, FailingDart())
    await dart.poll_job(ctx)  # 예외가 새어 나오면 실패
    assert ctx.bot.send_message.await_count == 0


async def test_아침_요약_발송(repo):
    yesterday = (datetime.now(dart.KST) - timedelta(days=1)).strftime("%Y%m%d")
    await repo.set_morning(100, True)
    await repo.add_watch(100, 100, make_company())
    await repo.insert_disclosure(make_record("R1", dt=yesterday), "t")

    ctx = _ctx(repo, StubDart())
    await dart.morning_job(ctx)

    assert ctx.bot.send_message.await_count == 1
    text = _texts(ctx)[0]
    assert "관심기업 공시 1건" in text
    assert "삼성전자" in text
    assert (await repo.get_morning(100)).last_morning_date == yesterday


async def test_아침_요약_공시없으면_발송없음(repo):
    await repo.set_morning(100, True)
    await repo.add_watch(100, 100, make_company())

    ctx = _ctx(repo, StubDart())
    await dart.morning_job(ctx)
    assert ctx.bot.send_message.await_count == 0


async def test_아침_요약_관심기업_없으면_발송없음(repo):
    yesterday = (datetime.now(dart.KST) - timedelta(days=1)).strftime("%Y%m%d")
    await repo.set_morning(100, True)
    await repo.insert_disclosure(make_record("R1", dt=yesterday), "t")

    ctx = _ctx(repo, StubDart())
    await dart.morning_job(ctx)
    assert ctx.bot.send_message.await_count == 0
