# QBK League Standings Embed

Live Spring/Winter standings widget for QBK, built for local testing first and Wix embedding second.

## Run locally
From `/Users/joshschwartz/Documents/New project/qbk-league-standings-embed`:

```bash
python3 server.py
```

Open:
- `http://localhost:8012/index.html`
- `http://localhost:8012/widget.html`
- `http://localhost:8012/api/standings`

## Credentials
The server uses:
1. `DASH_API_CLIENT_ID` + `DASH_API_SECRET` from the shell, or
2. `~/.codex/config.toml` under `mcp_servers.qbk-sports-admin.env`

## Query params
Supported on both `index.html` and `widget.html`:
- `season_id=104`
- `season_label=Spring 2026`
- `hide_sunday=1`
- `dedupe=1`

Example:

```text
http://localhost:8012/widget.html?season_id=104&season_label=Spring%202026&hide_sunday=1&dedupe=1
```

## Wix embed
Once deployed publicly, use:

```html
<iframe
  src="https://YOUR-DOMAIN/widget.html?season_id=104&season_label=Spring%202026&hide_sunday=1&dedupe=1"
  title="QBK League Standings"
  width="100%"
  height="1800"
  style="border:0; overflow:hidden;"
  loading="lazy"
></iframe>
```
