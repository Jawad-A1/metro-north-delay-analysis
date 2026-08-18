"""Shared color palette and Plotly theme for both Streamlit apps.

Colors are a validated colorblind-safe categorical order (fixed hue order,
never cycled or reassigned by rank) plus a fixed status palette for delay
risk tiers, so risk is always shown with an icon + label and never by hue
alone. Both apps (app.py, src/app.py) import from here to stay visually
consistent and keep the palette defined in exactly one place.
"""

import plotly.graph_objects as go
import plotly.io as pio

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE = "#2a78d6"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# Status palette (fixed - never reused for series identity, always paired
# with an icon + label since some steps are low-contrast on a light surface).
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

RISK_TIER_STATUS = {
    "Low": ("good", "\U0001F7E2"),
    "Medium": ("warning", "\U0001F7E1"),
    "High": ("serious", "\U0001F7E0"),
    "Very High": ("critical", "\U0001F534"),
}


def apply_plotly_theme() -> None:
    """Register and activate the shared 'metro_north' Plotly template."""
    pio.templates["metro_north"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font=dict(family=FONT_FAMILY, color=INK, size=13),
            title=dict(font=dict(color=INK, size=16)),
            xaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED)),
            yaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED)),
            legend=dict(font=dict(color=INK_SECONDARY)),
            margin=dict(l=10, r=10, t=40, b=10),
            hoverlabel=dict(bgcolor=SURFACE, font=dict(family=FONT_FAMILY, color=INK)),
        )
    )
    pio.templates.default = "metro_north"


def risk_tier_style(tier: str) -> tuple[str, str]:
    """(hex color, icon) for a risk tier, drawn from the fixed status palette."""
    status_key, icon = RISK_TIER_STATUS.get(tier, ("warning", "⚪"))
    return STATUS[status_key], icon
