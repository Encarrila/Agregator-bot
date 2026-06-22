"""Ledger anti-repetición: recuerda qué URLs ya se enviaron.

El cron de GitHub Actions es stateless, así que persistimos el registro en
state/seen.json y lo commiteamos de vuelta al repo (ver el workflow). En la
corrida siguiente filtramos lo ya visto para no repetir.

Poda automática: las entradas de más de RETENTION_DAYS se descartan, así el
archivo no crece para siempre.
"""
from __future__ import annotations

import datetime as dt
import json
import os

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "seen.json")
RETENTION_DAYS = 14


def _load_raw() -> list[dict]:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def load_seen() -> set[str]:
    """URLs ya enviadas en los últimos RETENTION_DAYS días."""
    return {e["url"] for e in _load_raw() if e.get("url")}


def record_seen(urls) -> int:
    """Agrega URLs nuevas al ledger, poda viejas y persiste. Devuelve cuántas
    URLs quedan registradas."""
    today = dt.date.today().isoformat()
    raw = _load_raw()
    have = {e.get("url") for e in raw}
    for u in urls:
        if u and u not in have:
            raw.append({"url": u, "date": today})
            have.add(u)

    cutoff = (dt.date.today() - dt.timedelta(days=RETENTION_DAYS)).isoformat()
    raw = [e for e in raw if e.get("date", "") >= cutoff]  # ISO ordena como fecha

    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    return len(raw)
