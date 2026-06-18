"""Render del digest a HTML para email.

Email-safe: tablas + CSS inline (muchos clientes descartan <style>). Diseño
sobrio tipo "digest": una columna, buena jerarquía tipográfica, acentos de color.
"""
from __future__ import annotations

import datetime as dt
import html

from sources.schema import SECTIONS

# Paleta
INK = "#1a1a2e"
MUTED = "#6b7280"
ACCENT = "#4f46e5"
BG = "#f4f4f7"
CARD = "#ffffff"
BORDER = "#e5e7eb"
POS = "#059669"
NEG = "#dc2626"


def _esc(s: str) -> str:
    return html.escape(s or "")


def _item_row(item: dict, section_key: str) -> str:
    title = _esc(item.get("title", ""))
    url = _esc(item.get("url", "#"))
    blurb = _esc(item.get("blurb", ""))

    # En mercados coloreamos según signo del movimiento.
    blurb_color = MUTED
    if section_key == "markets":
        if blurb.startswith("▲") or "+%" in blurb or "+" in blurb[:3]:
            blurb_color = POS
        elif blurb.startswith("▼") or "-" in blurb[:3]:
            blurb_color = NEG

    return f"""
    <tr><td style="padding:12px 0;border-bottom:1px solid {BORDER};">
      <a href="{url}" style="color:{INK};font-size:16px;font-weight:600;
         text-decoration:none;line-height:1.35;">{title}</a>
      <div style="color:{blurb_color};font-size:14px;line-height:1.5;margin-top:4px;">
        {blurb}</div>
    </td></tr>"""


def _section_block(title: str, rows_html: str) -> str:
    if not rows_html.strip():
        return ""
    return f"""
    <tr><td style="padding:26px 28px 6px 28px;">
      <h2 style="color:{INK};font-size:18px;margin:0 0 4px 0;">{title}</h2>
    </td></tr>
    <tr><td style="padding:0 28px 8px 28px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        {rows_html}
      </table>
    </td></tr>"""


def render_html(curated: dict) -> str:
    today = dt.date.today().strftime("%d/%m/%Y")
    intro = _esc(curated.get("intro", ""))
    sections_data = curated.get("sections", {})

    blocks = ""
    for sec in SECTIONS:
        items = sections_data.get(sec["key"], [])
        rows = "".join(_item_row(it, sec["key"]) for it in items)
        blocks += _section_block(sec["title"], rows)

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:{BG};
  font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
        style="max-width:600px;width:100%;background:{CARD};border-radius:14px;
        overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr><td style="background:{ACCENT};padding:28px;">
          <div style="color:#fff;font-size:22px;font-weight:700;">🧠 AI Daily Digest</div>
          <div style="color:#c7d2fe;font-size:14px;margin-top:4px;">{today}</div>
          {f'<div style="color:#e0e7ff;font-size:15px;margin-top:12px;line-height:1.5;">{intro}</div>' if intro else ''}
        </td></tr>

        {blocks}

        <!-- Footer -->
        <tr><td style="padding:24px 28px;color:{MUTED};font-size:12px;
          border-top:1px solid {BORDER};">
          Generado automáticamente · Fuentes: arXiv, Hugging Face, feeds RSS oficiales, Yahoo Finance.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def render_text(curated: dict) -> str:
    """Fallback en texto plano para clientes sin HTML."""
    lines = [f"AI Daily Digest — {dt.date.today().isoformat()}", ""]
    if curated.get("intro"):
        lines += [curated["intro"], ""]
    sections_data = curated.get("sections", {})
    for sec in SECTIONS:
        items = sections_data.get(sec["key"], [])
        if not items:
            continue
        lines.append(sec["title"])
        for it in items:
            lines.append(f"  • {it.get('title', '')}")
            if it.get("blurb"):
                lines.append(f"    {it['blurb']}")
            lines.append(f"    {it.get('url', '')}")
        lines.append("")
    return "\n".join(lines)
