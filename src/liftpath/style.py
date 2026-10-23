"""The one palette for all figures and the app. One fixed hue per method.

The categorical slots come from the dataviz reference palette (light mode) and passed its
validator in this order. Three slots are below 3:1 against the surface, so charts that use
them carry direct labels.
"""

import textwrap

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
MAGENTA = "#e87ba4"
GREEN = "#008300"
VIOLET = "#6250d6"

METHOD_COLORS = {
    "liftpath": BLUE,
    "raw_success": ORANGE,
    "liftpath_explore": AQUA,
    "user_cf": YELLOW,
    "popular": MAGENTA,
    "random": GREEN,
    "course_order": VIOLET,
    "none": MUTED,
}

# The app uses a dark theme (.streamlit/config.toml). The slide figures stay light. The dark
# chart slots are the dark steps of the same hues from the dataviz reference palette. They
# passed its validator on DARK_SURFACE and on DARK_BG (dark mode, all checks).
DARK_BG = "#0f1724"
DARK_SURFACE = "#172133"
DARK_SURFACE_2 = "#1e2a40"
DARK_BORDER = "#2a3750"
DARK_TEXT = "#e6e9ef"
DARK_TEXT_SECONDARY = "#b4bccb"
DARK_MUTED = "#8b95a7"
DARK_GRID = "#26324a"
# Plotly does not wrap titles. App chart titles longer than this wrap onto a second line.
TITLE_WRAP_CHARS = 40
TITLE_LINE_PX = 22
DARK_BLUE = "#3987e5"

LIGHT_TO_DARK = {
    BLUE: DARK_BLUE, ORANGE: "#d95926", AQUA: "#199e70", YELLOW: "#c98500",
    MAGENTA: "#d55181", GREEN: "#008300", VIOLET: "#9085e9",
    SURFACE: "rgba(0,0,0,0)", TEXT: DARK_TEXT, TEXT_SECONDARY: DARK_TEXT_SECONDARY,
    MUTED: DARK_MUTED, GRID: DARK_GRID, "#ffffff": DARK_SURFACE, "#c3c2b7": DARK_BORDER,
}

# Teacher view status colors. They mark facts about a student, not methods, and always come
# with a text label. Dark theme steps: each one is 4.5:1 or more on DARK_SURFACE.
STATUS_COLORS = {
    "go_back": "#ff8a73",
    "no_activity": "#f5b544",
    "next_step": "#6aa8ff",
    "no_change": "#a7b0bf",
}
STATUS_TINTS = {
    "go_back": "rgba(255,138,115,0.12)",
    "no_activity": "rgba(245,181,68,0.12)",
    "next_step": "rgba(106,168,255,0.12)",
    "no_change": "rgba(167,176,191,0.10)",
}
BORDER = DARK_BORDER


def to_dark(value):
    """Replace every light palette color in a Plotly figure dict with its dark step."""
    if isinstance(value, dict):
        return {k: to_dark(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_dark(v) for v in value]
    if isinstance(value, str):
        return LIGHT_TO_DARK.get(value.lower(), value)
    return value


def dark_figure(fig):
    """A copy of a Plotly figure for the dark app theme. Slide figures do not use it."""
    import plotly.graph_objects as go

    spec = fig.to_dict()
    spec["layout"].pop("template", None)
    title = spec["layout"].get("title", {})
    if len(title.get("text") or "") > TITLE_WRAP_CHARS and "<br>" not in title["text"]:
        lines = textwrap.wrap(title["text"], TITLE_WRAP_CHARS)
        title["text"] = "<br>".join(lines)
        margin = spec["layout"].setdefault("margin", {})
        extra = TITLE_LINE_PX * (len(lines) - 1)
        margin["t"] = margin.get("t", 100) + extra
        if spec["layout"].get("height"):
            spec["layout"]["height"] += extra
    out = go.Figure(to_dark(spec))
    axis = {"automargin": True, "gridcolor": DARK_GRID, "linecolor": DARK_BORDER,
            "zerolinecolor": DARK_MUTED,
            "tickfont": {"color": DARK_TEXT_SECONDARY},
            "title_font": {"color": DARK_TEXT_SECONDARY}}
    out.update_layout(template="none", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"color": DARK_TEXT, "family": "Source Sans, sans-serif"},
                      title_font={"color": DARK_TEXT}, legend={"bgcolor": "rgba(0,0,0,0)"},
                      hoverlabel={"bgcolor": DARK_SURFACE_2, "bordercolor": DARK_BORDER,
                                  "font": {"color": DARK_TEXT}})
    out.update_xaxes(**axis)
    out.update_yaxes(**axis)
    return out
