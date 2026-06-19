from sources.schema import Item, SECTIONS


def test_item_to_dict_roundtrip():
    it = Item(title="t", url="u", summary="s", source="arXiv", published="2026-06-18")
    d = it.to_dict()
    assert d["title"] == "t"
    assert d["meta"] == {}          # default_factory genera un dict nuevo
    assert set(d) == {"title", "url", "summary", "source", "published", "meta"}


def test_item_meta_is_isolated_between_instances():
    a = Item("a", "u", "s", "src")
    b = Item("b", "u", "s", "src")
    a.meta["x"] = 1
    assert b.meta == {}             # el default_factory evita el mutable compartido


def test_sections_keys_match_pipeline_buckets():
    keys = {s["key"] for s in SECTIONS}
    assert keys == {"papers", "news", "models", "markets"}
    assert all(s["title"] for s in SECTIONS)  # todas tienen título visible
