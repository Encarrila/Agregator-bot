from sources.schema import Item
from digest import curate


def _buckets():
    return {
        "papers": [Item(f"p{i}", "u", "abstract largo " * 50, "arXiv") for i in range(8)],
        "news": [Item("n1", "u", "s", "OpenAI")],
        "models": [],
        "markets": [Item("NVDA", "u", "▲ +1%", "Yahoo Finance")],
    }


def test_curate_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = curate(_buckets())

    assert "sections" in out and "intro" in out
    assert set(out["sections"]) == {"papers", "news", "models", "markets"}


def test_fallback_caps_at_five_items_per_section(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = curate(_buckets())
    assert len(out["sections"]["papers"]) == 5      # tope de 5 aunque haya 8
    assert out["sections"]["models"] == []          # sección vacía se respeta


def test_fallback_truncates_long_blurbs(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = curate(_buckets())
    assert all(len(it["blurb"]) <= 200 for it in out["sections"]["papers"])
