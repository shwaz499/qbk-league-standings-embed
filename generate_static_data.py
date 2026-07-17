#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from server import CLIENT

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
SEASONS = [
    ("111", "2026 Summer Leagues"),
]
VISIBLE_LEAGUE_TITLES = {"Monday 4s", "Thursday 6s"}
TEAM_NAME_OVERRIDES = {
    "Monday - Free Agents (2)": "Free Agent Team 2",
    "Free Agent Team - Mon Int": "Free Agent Team 1",
    "Third Thursday Free Agent Team": "Free Agent Team 3",
}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for season_id, season_label in SEASONS:
        payload = CLIENT.standings_for_season(
            season_id=season_id,
            season_label=season_label,
            hide_sunday=True,
            dedupe=True,
            force_refresh=True,
        )
        payload["leagues"] = [
            league for league in payload.get("leagues", [])
            if league.get("title") in VISIBLE_LEAGUE_TITLES
        ]
        for league in payload["leagues"]:
            for team in league.get("teams", []):
                team["team_name"] = TEAM_NAME_OVERRIDES.get(
                    team.get("team_name"), team.get("team_name")
                )
        payload["cached"] = False
        output_path = DATA_DIR / f"standings-{season_id}.json"
        output_path.write_text(json.dumps(payload, indent=2))
        manifest[season_id] = season_label

    (DATA_DIR / "manifest.json").write_text(json.dumps({"seasons": manifest}, indent=2))
    print(f"Wrote standings data to {DATA_DIR}")


if __name__ == "__main__":
    main()
