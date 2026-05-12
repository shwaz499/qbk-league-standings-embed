#!/usr/bin/env python3
"""Serve a live QBK league standings widget."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None


PROJECT_DIR = Path(__file__).resolve().parent
API_BASE = os.getenv("DASH_API_BASE", "https://api.dashplatform.com").rstrip("/")
DEFAULT_PORT = int(os.getenv("PORT", "8012"))
DEFAULT_SEASON_ID = os.getenv("QBK_STANDINGS_DEFAULT_SEASON_ID", "106")
DEFAULT_SEASON_LABEL = os.getenv("QBK_STANDINGS_DEFAULT_SEASON_LABEL", "Late Spring Leagues")
CACHE_TTL_SECONDS = int(os.getenv("QBK_STANDINGS_CACHE_TTL", "180"))
PAGE_SIZE = 500
DAY_ORDER = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}
SIZE_ORDER = {"4s": 1, "6s": 2, "2s": 3, "": 9}


def normalize_team_name(name: str | None) -> str:
    decoded = urllib.parse.unquote_plus((name or "").strip())
    decoded = re.sub(r"\s+", " ", decoded)
    return decoded


def title_for_league(name: str) -> str:
    title = name
    if "Monday" in name:
        day = "Monday"
    elif "Tuesday" in name:
        day = "Tuesday"
    elif "Wednesday" in name:
        day = "Wednesday"
    elif "Thursday" in name or "Thurs" in name:
        day = "Thursday"
    elif "Friday" in name:
        day = "Friday"
    elif "Saturday" in name:
        day = "Saturday"
    elif "Sunday" in name:
        day = "Sunday"
    else:
        return title

    size = ""
    if "4x4" in name:
        size = "4s"
    elif "6x6" in name:
        size = "6s"
    elif "2x2" in name:
        size = "2s"

    return f"{day} {size}".strip()


def league_sort_key(league: dict[str, Any]) -> tuple[int, int, str]:
    title = league.get("title") or ""
    parts = title.split()
    day = parts[0] if parts else ""
    size = parts[1] if len(parts) > 1 else ""
    return (DAY_ORDER.get(day, 99), SIZE_ORDER.get(size, 99), league.get("source_name") or title)


@dataclass
class TeamStanding:
    team_id: str
    team_name: str
    wins: int = 0
    losses: int = 0
    diff: int = 0
    gp: int = 0

    @property
    def win_pct(self) -> float:
        return self.wins / self.gp if self.gp else 0.0

    def to_dict(self, rank: int) -> dict[str, Any]:
        return {
            "rank": rank,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "w": self.wins,
            "l": self.losses,
            "win_pct": round(self.win_pct, 3),
            "win_pct_display": f"{self.win_pct:.3f}",
            "diff": self.diff,
            "gp": self.gp,
        }


class DashClient:
    def __init__(self) -> None:
        self.client_id, self.client_secret = self._load_credentials()
        self._http = self._build_http_client()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._season_cache: dict[tuple[str, bool, bool], tuple[float, dict[str, Any]]] = {}

    def _build_http_client(self) -> httpx.Client:
        verify: bool | str = True
        try:
            import certifi  # type: ignore

            verify = certifi.where()
        except Exception:
            verify = True

        return httpx.Client(
            base_url=API_BASE,
            timeout=30.0,
            verify=verify,
            headers={
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
        )

    def _load_credentials(self) -> tuple[str, str]:
        client_id = os.getenv("DASH_API_CLIENT_ID")
        client_secret = os.getenv("DASH_API_SECRET")
        if client_id and client_secret:
            return client_id, client_secret

        config_path = Path.home() / ".codex" / "config.toml"
        if tomllib is None or not config_path.exists():
            raise RuntimeError("Missing DASH credentials.")

        config = tomllib.loads(config_path.read_text())
        env = config.get("mcp_servers", {}).get("qbk-sports-admin", {}).get("env", {})
        client_id = env.get("DASH_API_CLIENT_ID")
        client_secret = env.get("DASH_API_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError("Could not find qbk-sports-admin credentials in ~/.codex/config.toml.")
        return client_id, client_secret

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, str | int] | None = None,
        body: dict[str, Any] | None = None,
        use_auth: bool = True,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if use_auth:
            headers["Authorization"] = f"Bearer {self._get_token()}"

        response = self._http.request(method, path, params=params, json=body, headers=headers)
        if response.status_code == 401 and use_auth:
            self._token = None
            self._token_expires_at = 0.0
            headers["Authorization"] = f"Bearer {self._get_token()}"
            response = self._http.request(method, path, params=params, json=body, headers=headers)

        if response.status_code >= 400:
            raise RuntimeError(f"Dash API {response.status_code}: {response.text[:320]}")
        return response.json()

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        response = self._request_json(
            "POST",
            "/v1/auth/token",
            body={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            use_auth=False,
        )
        token = response.get("access_token") or response.get("token")
        if not token:
            raise RuntimeError("Dash API auth returned no access token.")
        self._token = str(token)
        self._token_expires_at = now + int(response.get("expires_in", 900))
        return self._token

    def _paged_rows(self, path: str, params: dict[str, str | int] | None = None, max_pages: int = 25) -> list[dict[str, Any]]:
        params = dict(params or {})
        page = 1
        rows: list[dict[str, Any]] = []
        while page <= max_pages:
            page_params = dict(params)
            page_params.update({"page[size]": PAGE_SIZE, "page[number]": page})
            response = self._request_json("GET", path, params=page_params)
            batch = response.get("data", [])
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page += 1
        return rows

    def _fetch_leagues(self, season_id: str) -> list[dict[str, Any]]:
        rows = self._paged_rows("/api/v1/leagues", {"filter[season_id]": season_id}, max_pages=10)
        leagues: list[dict[str, Any]] = []
        for row in rows:
            attrs = row.get("attributes", {})
            name = str(attrs.get("name") or attrs.get("description") or row.get("id"))
            leagues.append({
                "id": str(row.get("id")),
                "source_name": name,
                "title": title_for_league(name),
            })
        leagues.sort(key=league_sort_key)
        return leagues

    def _fetch_teams_for_league(self, league_id: str) -> list[dict[str, str]]:
        rows = self._paged_rows("/api/v1/teams", {"filter[league_id]": league_id}, max_pages=10)
        teams: list[dict[str, str]] = []
        for row in rows:
            attrs = row.get("attributes", {})
            teams.append({
                "id": str(row.get("id")),
                "name": normalize_team_name(str(attrs.get("name") or attrs.get("title") or row.get("id"))),
            })
        return teams

    def _fetch_events_for_team_filter(self, filter_key: str, team_id: str) -> list[dict[str, Any]]:
        return self._paged_rows(
            "/api/v1/events",
            {f"filter[{filter_key}]": team_id, "filter[sub_type]": "regular"},
            max_pages=20,
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _compute_league_standings(self, league: dict[str, Any], dedupe: bool) -> dict[str, Any]:
        teams = self._fetch_teams_for_league(league["id"])
        team_ids = {team["id"] for team in teams}
        standings = {
            team["id"]: TeamStanding(team_id=team["id"], team_name=team["name"])
            for team in teams
        }

        event_rows: dict[str, dict[str, Any]] = {}
        requests: list[tuple[str, str]] = []
        for team_id in team_ids:
            requests.append(("hteam_id", team_id))
            requests.append(("vteam_id", team_id))

        with ThreadPoolExecutor(max_workers=min(16, max(1, len(requests)))) as pool:
            future_map = {
                pool.submit(self._fetch_events_for_team_filter, filter_key, team_id): (filter_key, team_id)
                for filter_key, team_id in requests
            }
            for future in as_completed(future_map):
                rows = future.result()
                for row in rows:
                    event_id = str(row.get("id"))
                    event_rows[event_id] = row

        for row in event_rows.values():
            attrs = row.get("attributes", {})
            home_id = str(attrs.get("hteam_id")) if attrs.get("hteam_id") is not None else None
            away_id = str(attrs.get("vteam_id")) if attrs.get("vteam_id") is not None else None
            if not home_id or not away_id:
                continue
            if home_id not in team_ids or away_id not in team_ids:
                continue

            home_score = self._safe_int(attrs.get("home_score"))
            away_score = self._safe_int(attrs.get("visiting_score"))
            if home_score is None or away_score is None:
                continue

            standings[home_id].gp += 1
            standings[away_id].gp += 1
            standings[home_id].diff += home_score - away_score
            standings[away_id].diff += away_score - home_score

            if home_score > away_score:
                standings[home_id].wins += 1
                standings[away_id].losses += 1
            elif away_score > home_score:
                standings[away_id].wins += 1
                standings[home_id].losses += 1

        rows = list(standings.values())
        if dedupe:
            deduped: dict[str, TeamStanding] = {}
            for row in rows:
                key = normalize_team_name(row.team_name).lower()
                existing = deduped.get(key)
                if existing is None:
                    deduped[key] = row
                    continue
                challenger = (row.gp, row.wins, row.diff, row.team_id)
                incumbent = (existing.gp, existing.wins, existing.diff, existing.team_id)
                if challenger > incumbent:
                    deduped[key] = row
            rows = list(deduped.values())

        rows.sort(key=lambda item: (-item.wins, -item.win_pct, -item.diff, -item.gp, item.team_name.lower()))
        return {
            "league_id": league["id"],
            "title": league["title"],
            "source_name": league["source_name"],
            "teams": [row.to_dict(rank=index + 1) for index, row in enumerate(rows)],
        }

    def standings_for_season(
        self,
        season_id: str,
        season_label: str,
        hide_sunday: bool,
        dedupe: bool,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        cache_key = (season_id, hide_sunday, dedupe)
        now = time.time()
        cached = self._season_cache.get(cache_key)
        if cached and not force_refresh and now - cached[0] < CACHE_TTL_SECONDS:
            payload = dict(cached[1])
            payload["cached"] = True
            payload["season_label"] = season_label
            return payload

        leagues = self._fetch_leagues(season_id)
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(leagues)))) as pool:
            futures = [pool.submit(self._compute_league_standings, league, dedupe) for league in leagues]
            league_payloads = [future.result() for future in futures]

        league_payloads.sort(key=league_sort_key)
        if hide_sunday:
            league_payloads = [item for item in league_payloads if item.get("title") != "Sunday 4s" and not str(item.get("title", "")).startswith("Sunday")]

        payload = {
            "season_id": season_id,
            "season_label": season_label,
            "generated_at": int(time.time()),
            "cached": False,
            "leagues": league_payloads,
        }
        self._season_cache[cache_key] = (now, payload)
        return payload


CLIENT = DashClient()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/standings":
            self._handle_standings(parsed)
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "qbk-league-standings-embed"})
            return
        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_standings(self, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        season_id = (query.get("season_id") or [DEFAULT_SEASON_ID])[0]
        season_label = (query.get("season_label") or [DEFAULT_SEASON_LABEL])[0]
        hide_sunday = (query.get("hide_sunday") or ["1"])[0] != "0"
        dedupe = (query.get("dedupe") or ["1"])[0] != "0"
        force_refresh = (query.get("refresh") or ["0"])[0] == "1"
        try:
            payload = CLIENT.standings_for_season(
                season_id,
                season_label,
                hide_sunday,
                dedupe,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=500)
            return
        self._send_json(payload)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", DEFAULT_PORT), Handler)
    print(f"QBK league standings widget running at http://localhost:{DEFAULT_PORT}")
    print(f"Widget view: http://localhost:{DEFAULT_PORT}/widget.html")
    print(f"Live API:    http://localhost:{DEFAULT_PORT}/api/standings")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
