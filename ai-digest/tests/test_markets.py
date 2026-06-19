from sources.schema import Item
from sources.markets import select_market_movers


def _movers(pcts):
    # ya ordenados por |pct| desc, como los entrega fetch_markets
    items = [Item(f"T{i}", "u", f"{p:+.2f}%", "Yahoo Finance", meta={"pct": p}) for i, p in enumerate(pcts)]
    return sorted(items, key=lambda it: abs(it.meta["pct"]), reverse=True)


def test_select_returns_subset_preserving_order():
    src = _movers([5.0, -3.0, 1.0, 0.1])
    out = select_market_movers(src)
    # invariantes que valen para passthrough Y para cualquier filtro razonable:
    assert len(out) <= len(src)                 # nunca agrega ítems
    titles = [it.title for it in src]
    assert [it.title for it in out] == [t for t in titles if t in {o.title for o in out}]


def test_select_handles_empty():
    assert select_market_movers([]) == []
