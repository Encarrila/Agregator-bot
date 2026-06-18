"""Movimiento bursátil de acciones/ETFs ligados a IA.

yfinance descarga datos de Yahoo Finance sin API key. Calculamos la variación
porcentual del último día de trading para cada ticker del watchlist.
"""
from __future__ import annotations

import yfinance as yf

from .schema import Item


def _last_change(ticker: str) -> dict | None:
    """Devuelve precio de cierre y variación % del último día con datos."""
    hist = yf.Ticker(ticker).history(period="5d")
    if hist.empty or len(hist) < 2:
        return None
    close = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2])
    pct = (close - prev) / prev * 100 if prev else 0.0
    return {"close": close, "pct": pct}


def select_market_movers(items: list[Item]) -> list[Item]:
    """Decide QUÉ movimientos de mercado entran al digest.

    Esta es una decisión editorial, no técnica: en un día plano mostrar 8
    tickers a ±0.2% es ruido. Implementá tu criterio de "vale la pena".

    Ideas / trade-offs a considerar:
      - Umbral por |pct|: ej. solo mostrar movimientos > 1.5%. Filtra ruido,
        pero un día MUY plano podría dejar la sección vacía.
      - Garantizar un mínimo: mostrar siempre al menos los top-3 aunque sean
        chicos, así la sección nunca queda vacía y mantenés contexto.
      - Tope máximo: nunca más de N (ej. 5) para no saturar el mail.

    `items` ya viene ordenado por |pct| descendente (mayor movimiento primero).

    TODO(vos): reemplazá este passthrough por tu lógica de selección.
    """
    # Passthrough temporal: muestra todo. Acá va tu criterio.
    return items


def fetch_markets(watchlist: dict[str, str]) -> list[Item]:
    """`watchlist` es {ticker: nombre_legible}. Devuelve un Item por ticker."""
    items: list[Item] = []
    for ticker, name in watchlist.items():
        data = _last_change(ticker)
        if data is None:
            continue
        arrow = "▲" if data["pct"] >= 0 else "▼"
        items.append(
            Item(
                title=f"{name} ({ticker})",
                url=f"https://finance.yahoo.com/quote/{ticker}",
                summary=f"{arrow} {data['pct']:+.2f}%  ·  ${data['close']:,.2f}",
                source="Yahoo Finance",
                meta={"ticker": ticker, "pct": data["pct"], "close": data["close"]},
            )
        )
    # Orden: mayores movimientos (en valor absoluto) primero — lo más "noticioso".
    items.sort(key=lambda it: abs(it.meta["pct"]), reverse=True)
    return select_market_movers(items)
