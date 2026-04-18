"""
UI helpers — reusable components and the `inject_theme()` function
that loads the Sheares Hall CSS on every page.

Import and call `inject_theme()` at the top of every Streamlit page.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st


_STYLES_PATH = Path(__file__).resolve().parent.parent / "static" / "styles.css"


def inject_theme() -> None:
    """Load the Sheares Hall custom CSS. Safe to call multiple times per page."""
    if not _STYLES_PATH.exists():
        return
    css = _STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def brand_stripe() -> None:
    """A thin orange gradient bar; useful just below a page title."""
    st.markdown('<div class="sh-brand-stripe"></div>', unsafe_allow_html=True)


def status_badge(status: str) -> str:
    """Return an HTML span for the given fundraiser/event status."""
    label = status.replace("_", " ").title()
    return f'<span class="status-badge status-{status}">{label}</span>'


def kpi(value: str, label: str, variant: str = "") -> str:
    """Return an HTML snippet for a KPI card.

    variant: "" | "accent" | "success" | "warning"
    """
    cls = f"sh-kpi sh-kpi-{variant}" if variant else "sh-kpi"
    return (
        f'<div class="{cls}">'
        f'<div class="sh-kpi-value">{value}</div>'
        f'<div class="sh-kpi-label">{label}</div>'
        f'</div>'
    )


def timeline(items: list[dict]) -> str:
    """Render a vertical status timeline.

    Each item: {"title": str, "meta": str, "state": "completed"|"current"|"rejected"|"pending"}
    Returns HTML to pass to st.markdown(..., unsafe_allow_html=True).
    """
    parts = ['<ul class="sh-timeline">']
    for it in items:
        state = it.get("state", "pending")
        parts.append(
            f'<li class="sh-timeline-item">'
            f'<span class="sh-timeline-dot {state}"></span>'
            f'<div class="sh-timeline-title">{it["title"]}</div>'
            f'<div class="sh-timeline-meta">{it.get("meta", "")}</div>'
            f'</li>'
        )
    parts.append("</ul>")
    return "".join(parts)
