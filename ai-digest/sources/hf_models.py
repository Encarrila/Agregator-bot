"""Modelos en tendencia de Hugging Face Hub.

La API pública del Hub (https://huggingface.co/api/models) permite ordenar por
distintos criterios. Pedimos por "likes" recientes para detectar lo que está
ganando tracción ahora, no los clásicos de siempre.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .schema import Item

HF_API = "https://huggingface.co/api/models"


def fetch_models(limit: int = 10, sort: str = "trendingScore") -> list[Item]:
    """Trae los modelos en tendencia del Hub.

    `sort` puede ser "trendingScore", "likes" o "downloads".
    """
    params = {
        "sort": sort,
        "direction": "-1",
        "limit": str(limit),
        "full": "true",
    }
    url = f"{HF_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ai-digest/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    items: list[Item] = []
    for m in data:
        model_id = m.get("id", "")
        pipeline = m.get("pipeline_tag", "")
        likes = m.get("likes", 0)
        downloads = m.get("downloads", 0)
        items.append(
            Item(
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                summary=f"Tarea: {pipeline or 'n/d'} · {likes} likes · {downloads:,} descargas",
                source="Hugging Face",
                published=(m.get("createdAt", "") or "")[:10],
                meta={"likes": likes, "downloads": downloads, "pipeline": pipeline},
            )
        )
    return items
