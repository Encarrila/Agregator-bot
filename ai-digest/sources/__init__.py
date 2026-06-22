"""Conectores de fuentes. Cada `fetch_*` devuelve list[Item]."""
from .papers import fetch_papers
from .news import fetch_news
from .hf_models import fetch_models
from .markets import fetch_markets
from .notion_sources import get_sources

__all__ = ["fetch_papers", "fetch_news", "fetch_models", "fetch_markets", "get_sources"]
