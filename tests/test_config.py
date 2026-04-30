import importlib
from pathlib import Path


def _reload_config(monkeypatch):
    import hsearch.config as config

    return importlib.reload(config)


def _clear_provider_env(monkeypatch):
    for key in [
        "BRAVE_API_KEY",
        "SERPER_API_KEY",
        "EXA_API_KEY",
        "TAVILY_API_KEY",
        "FIRECRAWL_API_KEY",
        "JINA_API_KEY",
        "HSEARCH_ENV_FILE",
        "HERMES_HOME",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_config_loads_active_hermes_profile_env(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    profile = tmp_path / ".hermes" / "profiles" / "bot8613"
    profile.mkdir(parents=True)
    (profile / ".env").write_text("TAVILY_API_KEY=tvly_profile\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(profile))
    sandbox_home = profile / "home"
    sandbox_home.mkdir()
    monkeypatch.setenv("HOME", str(sandbox_home))

    config = _reload_config(monkeypatch)

    assert config.get_key("tavily") == "tvly_profile"


def test_profile_env_wins_over_global_hermes_env(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    hermes_root = tmp_path / ".hermes"
    profile = hermes_root / "profiles" / "bot8613"
    profile.mkdir(parents=True)
    (hermes_root / ".env").write_text(
        "TAVILY_API_KEY=tvly_global\nEXA_API_KEY=exa_global\n", encoding="utf-8"
    )
    (profile / ".env").write_text("TAVILY_API_KEY=tvly_profile\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.setenv("HOME", str(profile / "home"))

    config = _reload_config(monkeypatch)

    assert config.get_key("tavily") == "tvly_profile"
    assert config.get_key("exa") == "exa_global"


def test_explicit_process_env_wins_over_env_files(monkeypatch, tmp_path):
    _clear_provider_env(monkeypatch)
    profile = tmp_path / ".hermes" / "profiles" / "bot8613"
    profile.mkdir(parents=True)
    (profile / ".env").write_text("TAVILY_API_KEY=tvly_profile\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.setenv("TAVILY_API_KEY", "tvly_process")

    config = _reload_config(monkeypatch)

    assert config.get_key("tavily") == "tvly_process"
