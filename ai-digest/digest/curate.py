"""Curado editorial con OpenAI.

Recibe los ítems crudos de todas las fuentes y, en UNA sola llamada, devuelve
una versión curada: selección, orden y un blurb corto en español por ítem.

Si no hay OPENAI_API_KEY, cae a un modo determinístico (recorta y limpia) para
que el pipeline nunca se rompa por falta de LLM.
"""
from __future__ import annotations

import json
import os

from sources.schema import Item
from config import OPENAI_MODEL


# ---------------------------------------------------------------------------
# GUÍA EDITORIAL — este es el "criterio" del newsletter.
# Es el lugar de mayor impacto: define QUÉ se considera relevante y CON QUÉ
# tono se escribe. Ajustalo a tu audiencia (vos, educador/a interesado/a en IA).
# ---------------------------------------------------------------------------
EDITORIAL_GUIDELINES = """\
Sos el editor de un newsletter diario sobre IA para un lector con perfil
educativo (le interesa el impacto de la IA en el aprendizaje y la enseñanza).

Criterios de selección por sección:
- papers: priorizá hallazgos con implicancia pedagógica concreta (tutores
  inteligentes, evaluación, alfabetización, equidad educativa). Descartá lo
  puramente teórico sin conexión con aprendizaje.
- news: priorizá lanzamientos/productos importantes y de fuentes oficiales.
  Evitá rumores y notas de opinión.
- models: destacá modelos útiles o novedosos; explicá en una frase para qué sirven.
- markets: resumí el clima general en una frase (qué subió/bajó fuerte y por qué,
  si se infiere del movimiento).
- trials: son FUENTES "a prueba" que el usuario evalúa sumar. Resumí qué publicó
  cada una para que pueda decidir si vale la pena seguirla. Mantené el nombre de
  la fuente visible en el title.

Tono: claro, conciso, español rioplatense neutro. Sin hype. Cada blurb: 1-2 frases.
"""

_SYSTEM = EDITORIAL_GUIDELINES + """

Devolvé EXCLUSIVAMENTE un JSON con esta forma:
{
  "sections": { "<clave_de_seccion>": [{"title": str, "url": str, "blurb": str}, ...] },
  "intro": "una frase que sintetice el día"
}
Incluí en "sections" UNA entrada por cada clave que recibís en el input (papers,
news, models, markets, trials, etc.). Máximo 5 ítems por sección. Usá los `url`
exactos que recibís, no inventes.
"""


def _compact(items: list[Item], n: int = 12) -> list[dict]:
    """Versión liviana para enviar al modelo (recorta el abstract)."""
    return [
        {"title": it.title, "url": it.url, "summary": it.summary[:400], "source": it.source}
        for it in items[:n]
    ]


def _fallback(buckets: dict[str, list[Item]]) -> dict:
    """Sin LLM: tomamos los primeros 5 de cada sección tal cual."""
    sections = {}
    for key, items in buckets.items():
        sections[key] = [
            {"title": it.title, "url": it.url, "blurb": it.summary[:200]}
            for it in items[:5]
        ]
    return {"sections": sections, "intro": "Resumen automático del día en IA."}


def curate(buckets: dict[str, list[Item]]) -> dict:
    """buckets = {"papers": [...], "news": [...], "models": [...], "markets": [...]}"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback(buckets)

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    payload = {key: _compact(items) for key, items in buckets.items()}

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.4,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, KeyError, IndexError):
        return _fallback(buckets)
