"""Contrato de datos compartido entre fuentes, curador y render.

Toda fuente (papers, news, modelos, mercados) devuelve una lista de `Item`.
El resto del pipeline (curado OpenAI, render HTML, envío) trabaja solo contra
este contrato y no necesita saber de dónde salió cada ítem.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Item:
    """Una unidad de contenido normalizada, venga de donde venga."""

    title: str
    url: str
    summary: str                       # texto crudo (abstract, descripción, etc.)
    source: str                        # "arXiv", "Hugging Face", "TechCrunch"...
    published: str = ""                # ISO date si está disponible
    meta: dict[str, Any] = field(default_factory=dict)  # extras por fuente

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Las secciones del newsletter, en el orden en que aparecerán en el mail.
# El `key` se usa internamente; el `title` es lo que ve el lector.
SECTIONS: list[dict[str, str]] = [
    {"key": "papers", "title": "📄 Papers — IA, aprendizaje y educación"},
    {"key": "news", "title": "🚀 Productos y lanzamientos"},
    {"key": "models", "title": "🤗 Nuevos modelos (Hugging Face)"},
    {"key": "markets", "title": "📈 Mercado: acciones de IA"},
]
