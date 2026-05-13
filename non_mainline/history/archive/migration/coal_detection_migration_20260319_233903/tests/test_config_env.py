"""
Config environment variable behavior tests.
"""

from config.config import Config


def test_config_dev_mode_from_coal_env(monkeypatch):
    monkeypatch.setenv("COAL_ENV", "DEV")
    cfg = Config()
    assert cfg.DEV_MODE is True

    monkeypatch.setenv("COAL_ENV", "PROD")
    cfg = Config()
    assert cfg.DEV_MODE is False


def test_config_use_real_grid_from_env(monkeypatch):
    monkeypatch.setenv("USE_REAL_GRID_IN_DEV", "True")
    cfg = Config()
    assert cfg.USE_REAL_GRID_IN_DEV is True

    monkeypatch.setenv("USE_REAL_GRID_IN_DEV", "false")
    cfg = Config()
    assert cfg.USE_REAL_GRID_IN_DEV is False

    monkeypatch.setenv("USE_REAL_GRID_IN_DEV", "invalid")
    cfg = Config()
    assert cfg.USE_REAL_GRID_IN_DEV is False
