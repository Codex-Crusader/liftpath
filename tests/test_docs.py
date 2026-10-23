"""Slide outline and demo script checks (BUILD2 Phase G)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_NOTE_WORDS = 60
N_SLIDES = 10
MAX_SPOKEN_WORDS = 470


def slides() -> list[str]:
    text = (ROOT / "docs" / "slides_outline.md").read_text(encoding="utf-8")
    return re.split(r"^## Slide \d+: ", text, flags=re.MULTILINE)[1:]


def test_slides_outline():
    found = slides()
    assert len(found) == N_SLIDES
    for slide in found:
        message = re.search(r"^Message: (.+)$", slide, flags=re.MULTILINE)
        figure = re.search(r"^Figure: `(.+)`$", slide, flags=re.MULTILINE)
        notes = re.search(r"^Notes: (.+)$", slide, flags=re.MULTILINE)
        assert message and figure and notes, slide[:40]
        assert (ROOT / figure.group(1)).exists(), figure.group(1)
        assert len(notes.group(1).split()) <= MAX_NOTE_WORDS, slide[:40]


def test_demo_script_length():
    text = (ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8")
    spoken = re.findall(r'^Say: "(.+)"$', text, flags=re.MULTILINE)
    assert spoken
    assert sum(len(s.split()) for s in spoken) <= MAX_SPOKEN_WORDS
    assert text.index("Teacher view") < text.index("Your route") < text.index("Simulator")
