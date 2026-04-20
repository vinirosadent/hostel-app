"""
UI helpers — reusable components and the `inject_theme()` function.
Import and call `inject_theme()` at the top of every Streamlit page.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st


_STYLES_PATH = Path(__file__).resolve().parent.parent / "static" / "styles.css"


def inject_theme() -> None:
    """Load the Sheares Hall CSS. Safe to call multiple times per page."""
    if not _STYLES_PATH.exists():
        return
    css = _STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def brand_stripe() -> None:
    st.markdown('<div class="sh-brand-stripe"></div>', unsafe_allow_html=True)


def context_breadcrumb(*parts: str) -> None:
    """Breadcrumb discreto — ex. 'Sheares Hall Ops / Fundraisers / Name'."""
    html = '<div class="sh-context">'
    for i, p in enumerate(parts):
        if i > 0:
            html += '<span class="sh-context-sep">/</span>'
        html += f'<span>{p}</span>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def status_badge(status: str) -> str:
    label = status.replace("_", " ").title()
    return f'<span class="status-badge status-{status}">{label}</span>'


def kpi(value: str, label: str, variant: str = "") -> str:
    cls = f"sh-kpi sh-kpi-{variant}" if variant else "sh-kpi"
    return (
        f'<div class="{cls}">'
        f'<div class="sh-kpi-value">{value}</div>'
        f'<div class="sh-kpi-label">{label}</div>'
        f'</div>'
    )


def progress_stepper(steps: list[dict], current_index: int,
                     rejected: bool = False) -> str:
    """Horizontal progress stepper (Stripe-style)."""
    html = '<div class="sh-stepper">'
    for i, step in enumerate(steps):
        if rejected and i == current_index:
            cls = "sh-step rejected"
            inner = "✕"
        elif i < current_index:
            cls = "sh-step completed"
            inner = "✓"
        elif i == current_index:
            cls = "sh-step current"
            inner = str(i + 1)
        else:
            cls = "sh-step"
            inner = str(i + 1)
        label = step.get("label", "")
        html += (
            f'<div class="{cls}">'
            f'<div class="sh-step-circle">{inner}</div>'
            f'<div class="sh-step-label">{label}</div>'
            f'</div>'
        )
    html += '</div>'
    return html


def empty_state(title: str, text: str, icon: str = "📭") -> None:
    st.markdown(
        f'<div class="sh-empty">'
        f'<div class="sh-empty-icon">{icon}</div>'
        f'<div class="sh-empty-title">{title}</div>'
        f'<div class="sh-empty-text">{text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def timeline(items: list[dict]) -> str:
    """Vertical workflow timeline. Each item: {title, meta, state}."""
    html = '<div class="sh-timeline">'
    for item in items:
        state = item.get("state", "pending")
        title = item.get("title", "")
        meta = item.get("meta", "")
        icon = {"completed": "✓", "current": "●", "rejected": "✕"}.get(state, "○")
        html += (
            f'<div class="sh-tl-item sh-tl-{state}">'
            f'<div class="sh-tl-icon">{icon}</div>'
            f'<div class="sh-tl-body">'
            f'<div class="sh-tl-title">{title}</div>'
            + (f'<div class="sh-tl-meta">{meta}</div>' if meta else "")
            + '</div></div>'
        )
    html += '</div>'
    return html


def workflow_progress_bar(stages: list[dict]) -> str:
    """Horizontal progress bar for fundraiser workflow.

    Each stage dict: {label, state, date_str}
    state: 'completed' | 'current' | 'pending' | 'rejected'
    date_str: formatted date string or '' (shown under label when completed)
    """
    icons = {"completed": "✓", "current": "●", "rejected": "✕", "pending": "○"}
    html = '<div class="sh-progress-wrap"><div class="sh-progress-bar">'
    for stage in stages:
        state = stage.get("state", "pending")
        label = stage.get("label", "")
        date_str = stage.get("date_str", "")
        icon = icons.get(state, "○")
        date_html = (
            f'<div class="sh-pb-date">{date_str}</div>' if date_str else
            '<div class="sh-pb-date">&nbsp;</div>'
        )
        html += (
            f'<div class="sh-pb-stage {state}">'
            f'<div class="sh-pb-dot">{icon}</div>'
            f'<div class="sh-pb-label">{label}</div>'
            f'{date_html}'
            f'</div>'
        )
    html += '</div></div>'
    return html


def corporate_table(
    columns: list[dict],
    rows: list[dict],
    empty_text: str = "No data",
    row_actions_fn=None,
) -> None:
    """
    Corporate-style data table rendered with st.columns + CSS classes.

    columns: list of {key, label, flex=1, align="left"|"right"|"center", mono=False}
    rows:    list of dicts whose keys match column "key" fields
    row_actions_fn: callable(row) -> None — renders action buttons in the last column
    """
    flexes = [c.get("flex", 1) for c in columns]
    has_actions = row_actions_fn is not None
    all_flexes = flexes + ([1] if has_actions else [])

    # ── Header row ──
    h_cols = st.columns(all_flexes)
    for i, col_spec in enumerate(columns):
        align_cls = f" sh-ctable-{col_spec.get('align', 'left')}"
        with h_cols[i]:
            st.markdown(
                f'<div class="sh-ctable-th{align_cls}">{col_spec["label"]}</div>',
                unsafe_allow_html=True,
            )
    if has_actions:
        with h_cols[-1]:
            st.markdown('<div class="sh-ctable-th"></div>', unsafe_allow_html=True)

    # ── Empty state ──
    if not rows:
        st.markdown(
            f'<div class="sh-ctable-empty-row">{empty_text}</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Data rows ──
    for row in rows:
        d_cols = st.columns(all_flexes)
        for i, col_spec in enumerate(columns):
            val = row.get(col_spec["key"])
            display = "—" if (val is None or val == "") else val
            parts = ["sh-ctable-td", f'sh-ctable-{col_spec.get("align", "left")}']
            if col_spec.get("mono"):
                parts.append("sh-ctable-mono")
            cls = " ".join(parts)
            with d_cols[i]:
                st.markdown(f'<div class="{cls}">{display}</div>', unsafe_allow_html=True)
        if has_actions:
            with d_cols[-1]:
                row_actions_fn(row)


def bucket_header(title: str, dot_class: str, count: int) -> None:
    st.markdown(
        f'<div class="sh-bucket-header">'
        f'<div class="sh-bucket-title">'
        f'<span class="sh-bucket-dot {dot_class}"></span>{title}'
        f'</div>'
        f'<div class="sh-bucket-count">{count}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
