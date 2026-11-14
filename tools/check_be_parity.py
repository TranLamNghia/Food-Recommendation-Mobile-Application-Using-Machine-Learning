#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 1 must produce the same numbers in all three implementations.

    tools/gen_buoc1_cases.py                    Python — the reference
    backend/Api/Nutrition/NutritionTargets.cs   C#     — the server
    mobile/lib/data/models/health_profile.dart  Dart   — the app

Why it is needed. The three run in three layers and never meet. When they
drift, **nothing reports it**: the app shows one calorie limit, the server
generates a meal plan from a different one, and both numbers look plausible.
The user has no way to tell, and neither does the developer — until somebody
works it out by hand.

That happened three times, and this checker caught all three on its first run:

  - **a 17/60/23 macro split in Dart** while the database's `DEFAULT` column
    and the API specification both said 15/60/25. Three sources, two numbers.
  - **`mealDistribution` 25/40/27/8 in the specification** while
    `meal_plan.dart` used the midpoints of the SYSTEM_ARCHITECTURE §3.1
    ranges, that is 27.5/37.5/27.5/7.5. Both sets are inside the ranges and
    both sum to 100%, so neither looks wrong.
  - **`bmiCategory: "normal"` for a BMI of 23.15 in the specification**, while
    the system uses the Asian thresholds 23/25 — where 23.15 is `overweight`.

THE THREE CHECKS
    1. regenerate `data/buoc1_cases.json` from the Python reference
    2. `dotnet test` — 44 C# assertions, no database needed
    3. `flutter test test/buoc1_parity_test.dart` — 32 Dart assertions

Run:
    python tools/check_be_parity.py
    python tools/check_be_parity.py --cases-only
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_buoc1_cases  # noqa: E402

CASES = ROOT / "data" / "buoc1_cases.json"
BACKEND = ROOT / "backend"
MOBILE = ROOT / "mobile"
DART_TEST = "test/buoc1_parity_test.dart"


def _use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def run(command: list[str], cwd: pathlib.Path) -> tuple[int, str] | None:
    """Run an external command; returns `None` when it is not on PATH.

    PATH has to be resolved explicitly with `shutil.which`: on Windows
    `flutter` and `dotnet` are `.bat`/`.cmd` files, and `CreateProcess` does
    not append the extension — calling `["flutter", ...]` directly raises
    `FileNotFoundError` even though that exact command works from a shell.
    """
    resolved = shutil.which(command[0])
    if resolved is None:
        return None
    r = subprocess.run(
        [resolved, *command[1:]], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main(argv: list[str] | None = None) -> int:
    _use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-only", action="store_true",
        help="write the case file only, do not run the two test suites",
    )
    args = parser.parse_args(argv)

    print("Audit: Step 1 — Python <-> C# <-> Dart")
    print("=" * 72)

    # -- 1. Generate the cases --------------------------------------------
    print("\n1. The Python reference")
    if gen_buoc1_cases.main([]) != 0:
        return 1
    if args.cases_only:
        return 0

    errors: list[str] = []

    # -- 2. C# -----------------------------------------------------------
    print("\n2. C# — backend/Api.Tests")
    result = run(["dotnet", "test", "--nologo"], BACKEND)
    if result is None:
        print("   !  `dotnet` is not on PATH — skipping the C# part")
        print("      run it by hand:  cd backend && dotnet test")
        errors.append("could not run the C# part (`dotnet` not on PATH)")
        code, output = 0, ""
    else:
        code, output = result
    for line in output.splitlines():
        if "Passed!" in line or "Failed!" in line or "error" in line.lower():
            print(f"   {line.strip()[:120]}")
    if code != 0:
        errors.append("dotnet test failed")

    # -- 3. Dart ---------------------------------------------------------
    print("\n3. Dart — mobile/test/buoc1_parity_test.dart")
    result = run(["flutter", "test", DART_TEST], MOBILE)
    if result is None:
        print("   !  `flutter` is not on PATH — skipping the Dart part")
        print(f"      run it by hand:  cd mobile && flutter test {DART_TEST}")
        errors.append("could not run the Dart part (`flutter` not on PATH)")
        code, output = 0, ""
    else:
        code, output = result
    lines = [line for line in output.splitlines() if line.strip()]
    if lines:
        print(f"   {lines[-1].strip()[:120]}")
    # Skipped cases must be STATED, never folded into the "passed" figure:
    # Dart's `Gender` has no `other`, so the three third-gender cases cannot
    # be checked on the Dart side. Staying silent about them makes a real gap
    # look covered. The matched strings are the Dart test's own Vietnamese
    # output, so they stay as they are.
    skipped = [
        line.strip() for line in output.splitlines()
        if "không có 'other'" in line or "DateTime.now()" in line
    ]
    if skipped:
        print(f"   {len(skipped)} cases skipped on the Dart side:")
        for line in sorted(set(skipped)):
            print(f"     ~ {line[:110]}")
    if code != 0:
        errors.append("flutter test failed")

    print("\n" + "=" * 72)
    if errors:
        print(f"{len(errors)} DIVERGENCES:")
        for x in errors:
            print("  -", x)
        print("\nFor the full output:")
        print("    cd backend && dotnet test")
        print(f"    cd mobile  && flutter test {DART_TEST}")
        return 1
    print("All three Step 1 implementations produce the same numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
