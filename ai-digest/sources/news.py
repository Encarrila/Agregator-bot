"""Noticias de productos/lanzamientos desde feeds RSS confiables.

Usamos RSS porque es estable, gratis y sin API key. La lista de feeds vive en
config.py para que puedas curar tus fuentes sin tocar esta lógica.
"""
from __future__ import annotations

import datetime as dt
import time

import feedparser

from .schema import Item


def _entry_date(entry) -> str:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        return dt.date.fromtimestamp(time.mktime(parsed)).isoformat()
    return ""


def fetch_news(feeds: dict[str, str], hours: int = 36, per_feed: int = 6) -> list[Item]:
    """Lee cada feed y devuelve entradas publicadas en las últimas `hours` horas.

    `feeds` es un dict {nombre_legible: url_rss}.
    """
    cutoff = dt.datetime.now() - dt.timedelta(hours=hours)
    items: list[Item] = []
    for name, url in feeds.items():
        try:
            parsed = feedparser.parse(url)
        except Exception:
            continue  # un feed caído no debe tumbar el digest entero
        count = 0
        for entry in parsed.entries:
            ts = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if ts and dt.datetime.fromtimestamp(time.mktime(ts)) < cutoff:
                continue
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            items.append(
                Item(
                    title=getattr(entry, "title", "(sin título)").strip(),
                    url=getattr(entry, "link", ""),
                    summary=summary,
                    source=name,
                    published=_entry_date(entry),
                )
            )
            count += 1
            if count >= per_feed:
                break
    return items
