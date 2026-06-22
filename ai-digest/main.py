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
from sources import fetch_papers, fetch_news, fetch_models, fetch_markets, get_sources
from digest import curate, render_html, render_text, send_email
from digest import state


def collect() -> dict:
    """Recolecta todas las fuentes con tolerancia a fallos."""
    buckets = {"papers": [], "news": [], "models": [], "markets": [], "trials": []}

    def safe(name, fn):
        try:
            buckets[name] = fn()
            print(f"  ✓ {name}: {len(buckets[name])} ítems")
        except Exception as e:  # noqa: BLE001 — una fuente caída no frena el resto
            print(f"  ✗ {name}: {e}", file=sys.stderr)

    print("Recolectando fuentes…")

    # Panel de Notion (opcional): fuentes aprobadas se suman a noticias,
    # las "en prueba" van a su propia sección para que el usuario decida.
    aprobadas, prueba = [], []
    try:
        aprobadas, prueba = get_sources()
        if aprobadas or prueba:
            print(f"  · Notion: {len(aprobadas)} aprobadas, {len(prueba)} en prueba")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ notion: {e}", file=sys.stderr)

    news_feeds = {**config.NEWS_FEEDS, **{s["nombre"]: s["url"] for s in aprobadas}}
    trial_feeds = {s["nombre"]: s["url"] for s in prueba}

    safe("papers", lambda: fetch_papers(config.LIMITS["papers"]))
    safe("news", lambda: fetch_news(
        news_feeds,
        hours=config.LIMITS["news_hours"],
        per_feed=config.LIMITS["news_per_feed"],
    ))
    safe("models", lambda: fetch_models(config.LIMITS["models"]))
    safe("markets", lambda: fetch_markets(config.WATCHLIST))
    if trial_feeds:
        safe("trials", lambda: fetch_news(
            trial_feeds,
            hours=config.LIMITS["trial_hours"],
            per_feed=config.LIMITS["trial_per_feed"],
        ))
    return buckets


def _shown_urls(curated: dict) -> list[str]:
    """URLs que efectivamente aparecieron en el digest enviado."""
    return [
        it.get("url")
        for sec in curated.get("sections", {}).values()
        for it in sec
        if it.get("url")
    ]


def build_digest() -> tuple[str, str, dict]:
    buckets = collect()

    # Anti-repetición: filtramos lo ya enviado en secciones de contenido.
    # markets/models quedan afuera: sus valores cambian a diario.
    seen = state.load_seen()
    for key in config.DEDUP_SECTIONS:
        kept = [it for it in buckets.get(key, []) if it.url not in seen]
        dropped = len(buckets.get(key, [])) - len(kept)
        if dropped:
            print(f"  · {key}: {dropped} ya enviados, filtrados")
        buckets[key] = kept

    print("Curando con OpenAI…")
    curated = curate(buckets)
    return render_html(curated), render_text(curated), curated


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Daily Digest")
    parser.add_argument("--dry-run", action="store_true",
                        help="Genera el HTML en preview.html sin enviar mail")
    args = parser.parse_args()

    html_body, text_body, curated = build_digest()

    if args.dry_run:
        with open("preview.html", "w", encoding="utf-8") as f:
            f.write(html_body)
        print("Dry-run: digest escrito en preview.html (no se envió mail, no se tocó el ledger).")
        return 0

    print("Enviando email…")
    result = send_email(html_body, text_body)
    print(f"Enviado: {result}")

    total = state.record_seen(_shown_urls(curated))
    print(f"Ledger actualizado: {total} URLs recordadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
