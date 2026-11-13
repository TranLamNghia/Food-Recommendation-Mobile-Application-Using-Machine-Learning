#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the palette's contrast ratios against WCAG 2.1.

Why this needs its own checker. Insufficient contrast is the kind of defect
**nobody sees while designing**: the designer has a good screen, moderate
room lighting and normal eyesight, so pale grey text on white still reads
fine to them. It only becomes a problem for real users, outdoors, on a cheap
screen, or with poor eyesight — which is to say exactly the people who never
sit next to you to complain.

Two defects it caught on its first run:

    textSecondary #8A8B90 on white      3.40:1  needs 4.50:1
    accent        #2AD2EE on white      1.82:1  needs 4.50:1

`accent` was worse still on `accentSoft` (1.65:1) — and that was the
background of two of the five places using it as a text colour.

## The WCAG 2.1 thresholds

    4.5:1   body text (under 18.66 px bold, or under 24 px regular)     AA
    3.0:1   large text, and **every** graphical component that must be
            distinguishable (icons, input borders, progress bars)        AA

Text in a disabled component is exempt under WCAG, so the table below marks
those pairs `exempt=True` with a reason — an exemption has to be stated, never
silently skipped.

## The pair list is hand-written

The (foreground, background) pairs cannot be detected automatically from the
Dart source: a background may be set by a parent widget ten levels up. So
`PAIRS` is hand-written, and each row records where it is used. A new usage
means a new row — the same approach `check_docs_sync.py` uses to keep the
documents from drifting from the schema.

Run:
    python tools/check_contrast.py

Note on language: the colour names are Dart identifiers and the quoted
strings inside the usage descriptions are the app's Vietnamese UI text, so
both stay as they are.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

COLOR_FILE = ROOT / "mobile" / "lib" / "core" / "theme" / "app_colors.dart"

#: The WCAG 2.1 AA thresholds.
THRESHOLD_BODY_TEXT = 4.5
THRESHOLD_LARGE_TEXT = 3.0
THRESHOLD_GRAPHICS = 3.0


@dataclass(frozen=True)
class Pair:
    """One (foreground, background) pair in real use, with its usage."""

<<<<<<< HEAD
    foreground: str
    background: str
    threshold: float
    used_for: str
    exempt: bool = False
    exemption_reason: str = ""
=======
    truoc: str
    sau: str
    threshold: float
    cho_dung: str
    mien_tru: bool = False
    ly_do_mien_tru: str = ""
>>>>>>> 57de08cb4d1bf75662c388cd72fd064d2816daba


#: Every colour pair in use. See the docstring: this is hand-written.
#:
#: Each row's threshold follows its **actual usage**, not the kind of colour.
#: The four macronutrient colours, for instance, are both progress-bar fills
#: (background `surfaceMuted`, threshold 3:1) and — for `carb` alone — the
#: text colour of a BMI label on a card surface (threshold 4.5:1). Assigning
#: one threshold to the whole group would miss exactly the stricter case.
PAIRS: tuple[Pair, ...] = (
    # -- Text on the three kinds of background --
    Pair("textPrimary", "surface", THRESHOLD_BODY_TEXT, "primary text on a card"),
    Pair(
        "textPrimary", "background", THRESHOLD_BODY_TEXT,
        "primary text on the page background",
    ),
    Pair(
        "textSecondary", "surface", THRESHOLD_BODY_TEXT,
        "secondary text on a card — app_theme's bodyLarge/bodyMedium",
    ),
    Pair(
        "textSecondary", "background", THRESHOLD_BODY_TEXT,
        "secondary text on the page background",
    ),
    Pair(
        "textSecondary", "surfaceMuted", THRESHOLD_BODY_TEXT,
        "secondary text on a pale grey area",
    ),
    Pair("textOnDark", "ink", THRESHOLD_BODY_TEXT, "text on a black button"),

    # -- The accent colour: text, icons, bar fills --
    Pair(
        "accentInk", "surface", THRESHOLD_BODY_TEXT,
        "accented numbers and labels on a card — motivation_step, option_card",
    ),
    Pair(
        "accentInk", "background", THRESHOLD_BODY_TEXT,
        "accented numbers on the page background",
    ),
    Pair(
        "accentInk", "accentSoft", THRESHOLD_BODY_TEXT,
        "accented label on the pale cyan block — survey_intro_screen",
    ),
    Pair(
        "accentInk", "surfaceMuted", THRESHOLD_GRAPHICS,
        "progress-bar fill in a grey track — calculating_screen, progress_screen",
    ),
    Pair(
        "ink", "accentSoft", THRESHOLD_BODY_TEXT,
        "black text on the cyan block — the ONLY usable way to use the raw cyan",
    ),

    # -- The four swipe directions. Three of these four are TEXT colours
    #    (`_Stat` in diary_screen, the BMI label in progress_screen), so the
    #    threshold is 4.5:1 rather than the 3:1 of a border.
    Pair(
        "like", "surface", THRESHOLD_BODY_TEXT,
        "the `Còn lại` text and the `Bình thường` BMI label",
    ),
    Pair(
        "dislike", "surface", THRESHOLD_BODY_TEXT,
        "the `Vượt` text and the `Béo phì` BMI label",
    ),
    Pair(
        "unknown", "surface", THRESHOLD_BODY_TEXT,
        "the `Thiếu cân` BMI label",
    ),
    Pair(
        "neutral", "surface", THRESHOLD_GRAPHICS,
        "the border and icon of the neutral direction",
    ),

    # -- The four macronutrient colours: bar fill on a `surfaceMuted` track --
    Pair(
        "kcal", "surfaceMuted", THRESHOLD_GRAPHICS,
        "the energy bar fill in diary_screen",
    ),
    Pair(
        "protein", "surfaceMuted", THRESHOLD_GRAPHICS,
        "the protein bar fill in energy_summary_card",
    ),
    Pair("carb", "surfaceMuted", THRESHOLD_GRAPHICS, "the carbohydrate bar fill"),
    Pair("fat", "surfaceMuted", THRESHOLD_GRAPHICS, "the fat bar fill"),
    #    `carb` is also the TEXT colour of the `Thừa cân` BMI label, so it has
    #    to clear the text threshold too — the row below is the stricter of
    #    its two usages.
    Pair(
        "carb", "surface", THRESHOLD_BODY_TEXT,
        "the `Thừa cân` BMI label in progress_screen",
    ),

    # -- Exemptions, each with a stated reason --
    Pair(
        "accent",
        "surface",
        THRESHOLD_GRAPHICS,
        "now only the ColorScheme's `seedColor` and `secondary`",
        exempt=True,
        exemption_reason=(
            "No surface is painted in this colour any more. It only seeds the "
            "ColorScheme and generates `accentSoft`; every text, icon and bar "
            "fill moved to `accentInk`. The raw cyan is usable only as a "
            "BACKGROUND with black text (11.55:1), never as a foreground on a "
            "light background."
        ),
    ),
    Pair(
        "textTertiary",
        "surface",
        THRESHOLD_BODY_TEXT,
        "the dimmed text of a disabled item, and the unit after a number",
        exempt=True,
        exemption_reason=(
            "WCAG 1.4.3 exempts the text of a disabled component. If this "
            "colour is ever used for active text, the exemption has to go."
        ),
    ),
    Pair(
        "border",
        "surface",
        THRESHOLD_GRAPHICS,
        "the divider line between two rows",
        exempt=True,
        exemption_reason=(
            "WCAG 1.4.11 does not apply to purely decorative lines — removing "
            "the divider loses no information, because the rows are already "
            "separated by whitespace. An INPUT border is not exempt."
        ),
    ),
)


def read_palette() -> dict[str, tuple[int, int, int]]:
    """Read the `Color(0xFFRRGGBB)` constants in `app_colors.dart`."""
    text = COLOR_FILE.read_text(encoding="utf-8")
    palette: dict[str, tuple[int, int, int]] = {}
    for m in re.finditer(
        r"static const (\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{8})\)", text
    ):
        name, hex8 = m.group(1), m.group(2)
        value = int(hex8, 16)
        palette[name] = (
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        )
    # Aliases pointing at another constant, for example `primary = ink`.
    for m in re.finditer(r"static const (\w+)\s*=\s*(\w+);", text):
        name, target = m.group(1), m.group(2)
        if target in palette and name not in palette:
            palette[name] = palette[target]
    return palette


def _linearize(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    """Relative luminance per WCAG 2.1."""
    r, g, b = (_linearize(channel) for channel in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def main() -> int:
    _env.use_utf8()
    print("Palette contrast check — WCAG 2.1 AA")
    print("=" * 72)

    palette = read_palette()
    print(f"Read {len(palette)} colours from {COLOR_FILE.relative_to(ROOT)}\n")

<<<<<<< HEAD
    failures: list[str] = []
    missing: list[str] = []
    passed = 0
    exempted = 0

    for pair in PAIRS:
        if pair.foreground not in palette or pair.background not in palette:
            absent = [
                n for n in (pair.foreground, pair.background) if n not in palette
            ]
            missing.append(
                f"{pair.foreground} on {pair.background}: "
                f"{', '.join(absent)} not declared"
            )
            continue

        ratio = contrast_ratio(palette[pair.foreground], palette[pair.background])
        label = f"{pair.foreground} on {pair.background}"
        figures = f"{ratio:5.2f}:1 needs {pair.threshold:.1f}:1"

        if ratio >= pair.threshold:
            passed += 1
            print(f"  ok   {label:34s} {figures}")
        elif pair.exempt:
            exempted += 1
            print(f"  ~    {label:34s} {figures}  EXEMPT")
            print(f"      {pair.exemption_reason}")
        else:
            failures.append(
                f"{label} = {ratio:.2f}:1, needs {pair.threshold:.1f}:1 "
                f"({_hex(palette[pair.foreground])} on "
                f"{_hex(palette[pair.background])}) — {pair.used_for}"
=======
    loi: list[str] = []
    missing: list[str] = []
    dat = 0
    mien = 0

    for cap in CAC_CAP:
        if cap.truoc not in mau or cap.sau not in mau:
            con = [t for t in (cap.truoc, cap.sau) if t not in mau]
            missing.append(f"{cap.truoc} trên {cap.sau}: chưa khai {', '.join(con)}")
            continue

        ty_so = tuong_phan(mau[cap.truoc], mau[cap.sau])
        nhan = f"{cap.truoc} trên {cap.sau}"
        so = f"{ty_so:5.2f}:1 cần {cap.threshold:.1f}:1"

        if ty_so >= cap.threshold:
            dat += 1
            print(f"  ✓ {nhan:34s} {so}")
        elif cap.mien_tru:
            mien += 1
            print(f"  ~ {nhan:34s} {so}  MIỄN TRỪ")
            print(f"      {cap.ly_do_mien_tru}")
        else:
            loi.append(
                f"{nhan} = {ty_so:.2f}:1, cần {cap.threshold:.1f}:1 "
                f"({_hex(mau[cap.truoc])} trên {_hex(mau[cap.sau])}) "
                f"— {cap.cho_dung}"
>>>>>>> 57de08cb4d1bf75662c388cd72fd064d2816daba
            )
            print(f"  BAD  {label:34s} {figures}")
            print(f"      {pair.used_for}")

    print("\n" + "=" * 72)
    if missing:
<<<<<<< HEAD
        print(f"{len(missing)} pairs could not be checked:")
=======
        print(f"{len(missing)} cặp không kiểm được:")
>>>>>>> 57de08cb4d1bf75662c388cd72fd064d2816daba
        for x in missing:
            print("  -", x)
    if failures:
        print(
            f"{passed} pairs passed, {exempted} exempt, {len(failures)} FAILED:"
        )
        for x in failures:
            print("  -", x)
        return 1
    if missing:
        return 1
    print(
        f"All {passed} pairs meet AA, with {exempted} exemptions each carrying "
        f"a stated reason."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
