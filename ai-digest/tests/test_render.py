from digest.render import render_html, render_text

CURATED = {
    "intro": "Día movido en IA.",
    "sections": {
        "papers": [{"title": "Tutores con LLM", "url": "https://arxiv.org/abs/1", "blurb": "Mejora aprendizaje."}],
        "news": [{"title": "OpenAI lanza X", "url": "https://openai.com/x", "blurb": "Nuevo producto."}],
        "models": [],
        "markets": [{"title": "NVIDIA (NVDA)", "url": "https://y/NVDA", "blurb": "▲ +2.10%  ·  $1,000.00"}],
    },
}


def test_render_html_includes_content_and_intro():
    html = render_html(CURATED)
    assert "<!DOCTYPE html>" in html
    assert "Tutores con LLM" in html
    assert "Día movido en IA." in html
    assert "https://openai.com/x" in html


def test_render_html_skips_empty_sections():
    html = render_html(CURATED)
    # 'models' está vacío: su título no debe aparecer.
    assert "Nuevos modelos" not in html
    # las secciones con contenido sí aparecen.
    assert "Papers" in html and "Mercado" in html


def test_render_html_escapes_user_content():
    evil = {"sections": {"papers": [{"title": "<script>x</script>", "url": "#", "blurb": ""}]}}
    html = render_html(evil)
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_text_lists_items():
    txt = render_text(CURATED)
    assert "NVIDIA (NVDA)" in txt
    assert "https://arxiv.org/abs/1" in txt
