"""The one palette for all figures and the app. One fixed color per method.

The categorical slots come from the dataviz reference palette (light mode) and passed its
validator in this order. Three slots are below 3:1 against the surface, so charts that use
them carry direct labels.
"""

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
