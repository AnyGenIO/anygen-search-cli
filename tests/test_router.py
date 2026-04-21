from hsearch.router import providers_for_mode, MODE_MAP


def test_modes_defined():
    for mode in ["default", "news", "academic", "code", "general", "realtime"]:
        assert mode in MODE_MAP


def test_routing_picks_configured(monkeypatch):
    # All keys are populated by conftest, so we should get the preferred providers.
    assert providers_for_mode("news") == ["brave", "serper"]
    assert providers_for_mode("academic") == ["exa"]
    assert providers_for_mode("realtime") == ["serper"]


def test_unknown_mode_falls_back_to_default():
    assert providers_for_mode("nonsense") == providers_for_mode("default")
