"""Configuración del digest. Editá libremente estas listas: son tus fuentes
y tu watchlist, no lógica del programa.

Los secretos (API keys, destinatario) NO van acá: se leen de variables de
entorno / .env (ver .env.example).
"""
from __future__ import annotations

import os

# --- Destinatario y remitente del mail -------------------------------------
# Resend exige que el "from" use un dominio verificado en tu cuenta.
# Para probar rápido podés usar el sandbox "onboarding@resend.dev".
MAIL_FROM = os.getenv("MAIL_FROM", "AI Digest <onboarding@resend.dev>")
MAIL_TO = os.getenv("MAIL_TO", "ezeuropa@hotmail.com")
MAIL_SUBJECT_PREFIX = "🧠 AI Daily Digest"

# --- Feeds de noticias (nombre legible -> URL RSS) -------------------------
# Curá esta lista a gusto. Fuentes oficiales > agregadores de terceros.
NEWS_FEEDS: dict[str, str] = {
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "MIT Tech Review": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
}

# --- Watchlist bursátil (ticker -> nombre legible) -------------------------
# Acciones y ETFs con alta exposición a IA.
WATCHLIST: dict[str, str] = {
    "NVDA": "NVIDIA",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "META": "Meta",
    "AMD": "AMD",
    "TSM": "TSMC",
    "PLTR": "Palantir",
    "BOTZ": "ETF Robótica/IA",
}

# --- Cuántos ítems pedir por fuente ----------------------------------------
LIMITS = {
    "papers": 12,
    "models": 10,
    "news_hours": 36,    # ventana de noticias recientes
    "news_per_feed": 6,
    "trial_hours": 72,   # ventana más amplia para fuentes "a prueba"
    "trial_per_feed": 3,
}

# --- Panel de fuentes en Notion (opcional) ---------------------------------
# Si NOTION_TOKEN y NOTION_SOURCES_DB están seteados, el digest lee fuentes
# extra desde una base de Notion (ver sources/notion_sources.py). Si no, se
# usa solo NEWS_FEEDS de arriba. La base tiene columnas:
#   Nombre (title) · URL (url) · Tipo (select) · Estado (select: Aprobada/En prueba/Rechazada)

# --- Anti-repetición --------------------------------------------------------
# Secciones a las que se aplica el ledger de "ya enviado". markets y models
# quedan afuera: sus valores cambian a diario y repetir el ítem es esperado.
DEDUP_SECTIONS = {"papers", "news", "trials"}

# --- Curado con OpenAI ------------------------------------------------------
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
