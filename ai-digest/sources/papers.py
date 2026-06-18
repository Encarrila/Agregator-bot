"""Papers recientes de arXiv: IA cruzada con aprendizaje / educación.

arXiv expone una API Atom pública y gratuita (sin API key). Filtramos por
categorías de IA (cs.AI, cs.CL, cs.LG) y por términos de educación/aprendizaje,
ordenando por fecha de envío para quedarnos con lo más nuevo.
"""
from __future__ import annotations

import datetime as dt
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .schema import Item

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"

# Categorías de IA + términos que acotan al impacto en aprendizaje/educación.
# La consulta booleana de arXiv: (cat:cs.AI OR ...) AND (all:education OR ...)
_CATS = ["cs.AI", "cs.CL", "cs.LG", "cs.CY"]
_EDU_TERMS = [
    "education", "learning analytics", "tutoring", "student",
    "pedagog", "classroom", "literacy", "curriculum",
]


def _build_query() -> str:
    cats = " OR ".join(f"cat:{c}" for c in _CATS)
    edu = " OR ".join(f'all:"{t}"' for t in _EDU_TERMS)
    return f"({cats}) AND ({edu})"


def fetch_papers(max_results: int = 12) -> list[Item]:
    """Trae los papers más recientes de IA con foco educativo."""
    params = {
        "search_query": _build_query(),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    items: list[Item] = []
    for entry in root.findall(f"{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip().replace("\n", " ")
        summary = (entry.findtext(f"{ATOM}summary") or "").strip().replace("\n", " ")
        published = (entry.findtext(f"{ATOM}published") or "")[:10]
        # El link "alternate" (HTML) es más útil que el id crudo.
        link = entry.findtext(f"{ATOM}id") or ""
        for l in entry.findall(f"{ATOM}link"):
            if l.get("rel") == "alternate":
                link = l.get("href", link)
        authors = [
            (a.findtext(f"{ATOM}name") or "").strip()
            for a in entry.findall(f"{ATOM}author")
        ]
        items.append(
            Item(
                title=title,
                url=link,
                summary=summary,
                source="arXiv",
                published=published,
                meta={"authors": authors[:4]},
            )
        )
    return items


if __name__ == "__main__":  # smoke test manual
    for it in fetch_papers(3):
        print(it.published, "-", it.title)
