from sources.notion_sources import parse_row


def _row(nombre="", url=None, tipo=None, estado=None):
    def sel(v):
        return {"select": {"name": v} if v else None}
    return {
        "properties": {
            "Nombre": {"title": [{"plain_text": nombre}]} if nombre else {"title": []},
            "URL": {"url": url},
            "Tipo": sel(tipo),
            "Estado": sel(estado),
        }
    }


def test_parse_row_extracts_fields():
    src = parse_row(_row("Karpathy Blog", "https://k.io/feed", "Blog", "Aprobada"))
    assert src == {
        "nombre": "Karpathy Blog",
        "url": "https://k.io/feed",
        "tipo": "Blog",
        "estado": "Aprobada",
    }


def test_parse_row_without_url_is_skipped():
    assert parse_row(_row("Sin URL", url=None)) is None


def test_parse_row_falls_back_to_url_when_no_name():
    src = parse_row(_row("", "https://x.io/feed", "RSS", "En prueba"))
    assert src["nombre"] == "https://x.io/feed"   # usa la URL como nombre


def test_parse_row_handles_empty_select():
    src = parse_row(_row("Algo", "https://a.io", tipo=None, estado=None))
    assert src["tipo"] == "" and src["estado"] == ""
