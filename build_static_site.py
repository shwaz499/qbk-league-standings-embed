#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
DATA_DIR = PROJECT_DIR / "data"
FILES_TO_COPY = [
    "index.html",
    "widget.html",
    "app.js",
    "styles.css",
]


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES_TO_COPY:
        shutil.copy2(PROJECT_DIR / name, DIST_DIR / name)

    target_data_dir = DIST_DIR / "data"
    if target_data_dir.exists():
        shutil.rmtree(target_data_dir)
    shutil.copytree(DATA_DIR, target_data_dir)
    print(f"Built static site in {DIST_DIR}")


if __name__ == "__main__":
    main()
