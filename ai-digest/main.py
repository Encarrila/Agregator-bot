"""Orquestador del digest diario — el "loop" que dispara GitHub Actions.

Flujo: recolectar fuentes -> curar con OpenAI -> renderizar HTML -> enviar.
Cada fuente está aislada en try/except: si una falla, el digest sale igual con
el resto. Soporta --dry-run para generar el HTML sin enviar mail.
"""
from __future__ import annotations

import argparse
import sys

# La consola de Windows usa cp1252 por defecto y no puede imprimir ✓/✗/emojis.
# Forzamos UTF-8 en stdout/stderr (inocuo en Linux/CI, que ya usan UTF-8).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Carga .env para corridas locales. En CI (GitHub Actions) las keys vienen de
# los secrets como variables de entorno, así que esto es inocuo si no hay .env.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import config
from sources import fetch_papers, fetch_news, fetch_models, fetch_markets
from digest import curate, render_html, render_text, send_email


def collect() -> dict:
    """Recolecta todas las fuentes con tolerancia a fallos."""
    buckets = {"papers": [], "news": [], "models": [], "markets": []}

    def safe(name, fn):
        try:
            buckets[name] = fn()
            print(f"  ✓ {name}: {len(buckets[name])} ítems")
        except Exception as e:  # noqa: BLE001 — una fuente caída no frena el resto
            print(f"  ✗ {name}: {e}", file=sys.stderr)

    print("Recolectando fuentes…")
    safe("papers", lambda: fetch_papers(config.LIMITS["papers"]))
    safe("news", lambda: fetch_news(
        config.NEWS_FEEDS,
        hours=config.LIMITS["news_hours"],
        per_feed=config.LIMITS["news_per_feed"],
    ))
    safe("models", lambda: fetch_models(config.LIMITS["models"]))
    safe("markets", lambda: fetch_markets(config.WATCHLIST))
    return buckets


def build_digest() -> tuple[str, str]:
    buckets = collect()
    print("Curando con OpenAI…")
    curated = curate(buckets)
    return render_html(curated), render_text(curated)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Daily Digest")
    parser.add_argument("--dry-run", action="store_true",
                        help="Genera el HTML en preview.html sin enviar mail")
    args = parser.parse_args()

    html_body, text_body = build_digest()

    if args.dry_run:
        with open("preview.html", "w", encoding="utf-8") as f:
            f.write(html_body)
        print("Dry-run: digest escrito en preview.html (no se envió mail).")
        return 0

    print("Enviando email…")
    result = send_email(html_body, text_body)
    print(f"Enviado: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
