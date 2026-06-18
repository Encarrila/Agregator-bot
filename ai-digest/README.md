# 🧠 AI Daily Digest

Newsletter diario por email con novedades de IA, curado con OpenAI y enviado
automáticamente cada mañana vía GitHub Actions.

## Secciones

| Sección | Fuente |
|---|---|
| 📄 Papers (IA + educación/aprendizaje) | arXiv |
| 🚀 Productos y lanzamientos | Feeds RSS oficiales (OpenAI, Google AI, HF, etc.) |
| 🤗 Nuevos modelos | Hugging Face Hub API |
| 📈 Mercado de acciones de IA | Yahoo Finance (yfinance) |

## Arquitectura

```
sources/  → conectores (cada uno devuelve list[Item], contrato en schema.py)
digest/   → curate (OpenAI) · render (HTML) · send (Resend)
main.py   → orquesta: recolectar → curar → renderizar → enviar
.github/workflows/daily-digest.yml → cron diario (el "loop")
```

Cada fuente está aislada: si una se cae, el digest sale con el resto.
Si falta `OPENAI_API_KEY`, el curado cae a un modo determinístico (sigue andando).

## Probar localmente

```bash
cd ai-digest
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env        # completá tus keys

# Generar el HTML sin enviar mail:
python main.py --dry-run    # escribe preview.html

# Enviar de verdad:
python main.py
```

## Desplegar (GitHub Actions)

1. Subí el repo a GitHub.
2. En **Settings → Secrets and variables → Actions**, creá estos secrets:
   - `OPENAI_API_KEY`, `OPENAI_MODEL` (ej. `gpt-4o-mini`)
   - `RESEND_API_KEY`
   - `MAIL_FROM` (dominio verificado en Resend, o `onboarding@resend.dev` para probar)
   - `MAIL_TO`
3. Pestaña **Actions → AI Daily Digest → Run workflow** para probar a mano.
4. A partir de ahí corre solo cada día a las 11:00 UTC (~08:00 ART). Cambiá el
   `cron` en el workflow para ajustar el horario.

## Personalizar

- **Fuentes y watchlist**: editá `config.py` (`NEWS_FEEDS`, `WATCHLIST`).
- **Criterio editorial / tono**: editá `EDITORIAL_GUIDELINES` en `digest/curate.py`.
