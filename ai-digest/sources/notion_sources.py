"""Lee las fuentes configuradas desde una base de Notion (el "panel").

La base tiene columnas: Nombre (title), URL (url), Tipo (select), Estado (select).
El cron usa su propio token de integración de Notion (NOTION_TOKEN) y el id de
la base (NOTION_SOURCES_DB), ambos como variables de entorno / secrets.

Si falta configuración, devuelve listas vacías: el digest sigue andando sin Notion.
"""
from __future__ import annotations

import os


def _title(prop: dict | None) -> str:
    if not prop:
        return ""
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()


def _select(prop: dict | None) -> str:
    if not prop:
        return ""
    sel = prop.get("select")
    return (sel or {}).get("name", "") if sel else ""


def parse_row(row: dict) -> dict | None:
    """Convierte una fila de Notion en {nombre, url, tipo, estado}.

    Devuelve None si la fila no tiene URL (inservible como fuente).
    Separado de la query para poder testearlo sin red.
    """
    props = row.get("properties", {})
    url = (props.get("URL") or {}).get("url")
    if not url:
        return None
    return {
        "nombre": _title(props.get("Nombre")) or url,
        "url": url,
        "tipo": _select(props.get("Tipo")),
        "estado": _select(props.get("Estado")),
    }


def get_sources() -> tuple[list[dict], list[dict]]:
    """Devuelve (aprobadas, en_prueba). Vacías si Notion no está configurado."""
    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_SOURCES_DB")
    if not (token and db_id):
        return [], []

    from notion_client import Client

    client = Client(auth=token)
    rows: list[dict] = []
    cursor: str | None = None
    while True:
        resp = client.databases.query(database_id=db_id, start_cursor=cursor)
        rows.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    aprobadas, prueba = [], []
    for row in rows:
        src = parse_row(row)
        if src is None:
            continue
        if src["estado"] == "Aprobada":
            aprobadas.append(src)
        elif src["estado"] == "En prueba":
            prueba.append(src)
    return aprobadas, prueba
