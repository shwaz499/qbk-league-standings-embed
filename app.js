(() => {
  const params = new URLSearchParams(window.location.search);
  const seasonId = params.get("season_id") || "104";
  const seasonLabelOverride = params.get("season_label") || "Spring 2026";
  const hideSunday = params.get("hide_sunday") !== "0";
  const dedupe = params.get("dedupe") !== "0";

  const els = {
    standingsGrid: document.getElementById("standings-grid"),
    widgetTitle: document.getElementById("widget-title"),
    template: document.getElementById("league-template"),
  };

  function renderEmpty(message, className = "empty-state") {
    els.standingsGrid.innerHTML = `<div class="${className}">${message}</div>`;
  }

  function renderLeague(league) {
    const fragment = els.template.content.cloneNode(true);
    fragment.querySelector(".league-title").textContent = league.title || league.source_name;
    const tbody = fragment.querySelector("tbody");

    if (!league.teams.length) {
      const emptyRow = document.createElement("tr");
      emptyRow.innerHTML = '<td colspan="7" class="empty-state">No scored regular-season matches yet.</td>';
      tbody.appendChild(emptyRow);
      return fragment;
    }

    league.teams.forEach((team) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><span class="rank-chip">${team.rank}</span></td>
        <td class="team-cell">${team.team_name}</td>
        <td data-label="W">${team.w}</td>
        <td data-label="L">${team.l}</td>
        <td data-label="Win %">${team.win_pct_display}</td>
        <td data-label="Diff">${team.diff > 0 ? `+${team.diff}` : team.diff}</td>
        <td data-label="GP">${team.gp}</td>
      `;
      tbody.appendChild(row);
    });

    return fragment;
  }

  async function loadStandings(force = false) {
    const endpoint = new URL("/api/standings", window.location.origin);
    endpoint.searchParams.set("season_id", seasonId);
    endpoint.searchParams.set("season_label", seasonLabelOverride);
    endpoint.searchParams.set("hide_sunday", hideSunday ? "1" : "0");
    endpoint.searchParams.set("dedupe", dedupe ? "1" : "0");
    if (force) {
      endpoint.searchParams.set("refresh", "1");
      endpoint.searchParams.set("_ts", String(Date.now()));
    }

    renderEmpty("Loading live standings...", "is-loading");

    try {
      const response = await fetch(endpoint, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }
      const payload = await response.json();
      if (els.widgetTitle) {
        els.widgetTitle.textContent = `${payload.season_label || seasonLabelOverride} League Standings`;
      }

      if (!payload.leagues || !payload.leagues.length) {
        renderEmpty("No leagues returned for this season.");
        return;
      }

      els.standingsGrid.innerHTML = "";
      payload.leagues.forEach((league) => {
        els.standingsGrid.appendChild(renderLeague(league));
      });
    } catch (error) {
      console.error(error);
      renderEmpty(`Could not load standings. ${error.message}`, "is-error");
    }
  }

  loadStandings(false);
})();
