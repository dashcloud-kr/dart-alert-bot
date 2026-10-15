"""Config 로딩/검증 테스트."""

from __future__ import annotations

import pytest

from app.config import Config, ConfigError

BASE_ENV = {"TELEGRAM_BOT_TOKEN": "123456:ABC-DEF", "DART_API_KEY": "dart-key"}


def test_from_env_필수값과_기본값():
    config = Config.from_env(BASE_ENV)
    assert config.bot_token == "123456:ABC-DEF"
    assert config.dart_api_key == "dart-key"
    assert config.db_path == "data/bot.db"
    assert config.admin_chat_id is None
    assert config.log_level == "INFO"


def test_from_env_토큰_없으면_에러():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        Config.from_env({"DART_API_KEY": "dart-key"})


def test_from_env_토큰_형식_검증():
    with pytest.raises(ConfigError, match="형식"):
        Config.from_env({"TELEGRAM_BOT_TOKEN": "not-a-token", "DART_API_KEY": "k"})


def test_from_env_DART키_없으면_에러():
    with pytest.raises(ConfigError, match="DART_API_KEY"):
        Config.from_env({"TELEGRAM_BOT_TOKEN": "1:A"})


def test_from_env_admin_chat_id_파싱():
    config = Config.from_env({**BASE_ENV, "ADMIN_CHAT_ID": "-100123"})
    assert config.admin_chat_id == -100123


def test_from_env_admin_chat_id_숫자_아니면_에러():
    with pytest.raises(ConfigError, match="ADMIN_CHAT_ID"):
        Config.from_env({**BASE_ENV, "ADMIN_CHAT_ID": "abc"})


def test_from_env_빈_문자열은_기본값으로():
    config = Config.from_env({**BASE_ENV, "DB_PATH": "  ", "LOG_LEVEL": ""})
    assert config.db_path == "data/bot.db"
    assert config.log_level == "INFO"


def test_from_env_로그레벨_대문자_정규화():
    config = Config.from_env({**BASE_ENV, "LOG_LEVEL": "debug"})
    assert config.log_level == "DEBUG"
