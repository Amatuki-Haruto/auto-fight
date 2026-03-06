"""config モジュールのテスト"""


def test_config_import():
    import config
    assert hasattr(config, "BACKEND_URL")
    assert hasattr(config, "HOME_URL")
    assert hasattr(config, "USER_DATA_DIR")
    assert hasattr(config, "SELECTOR_EXPLORE")
    assert len(config.SELECTOR_EXPLORE) >= 1
    assert config.WAIT_START[0] < config.WAIT_START[1]
    assert config.WAIT_AFTER_RETURN[0] < config.WAIT_AFTER_RETURN[1]
    assert hasattr(config, "FORCE_STOP_PATTERNS")
    assert "あなたはLv100になりました" in config.FORCE_STOP_PATTERNS
