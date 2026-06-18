"""Pipeline de digest: curado, render y envío."""
from .curate import curate
from .render import render_html, render_text
from .send import send_email

__all__ = ["curate", "render_html", "render_text", "send_email"]
