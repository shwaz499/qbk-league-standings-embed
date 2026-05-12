(() => {
  const body = document.body;
  const seasonId = body.dataset.seasonId || "106";
  const seasonLabel = body.dataset.seasonLabel || "Late Spring 2026";
  const leagueTitle = body.dataset.leagueTitle || "";
  const hideSunday = body.dataset.hideSunday !== "0";
  const dedupe = body.dataset.dedupe !== "0";

  const els = {
    leagueTitle: document.getElementById("tv-league-title"),
    tableBody: document.getElementById("tv-table-body"),
    emptyState: document.getElementById("tv-empty-state"),
  };

  function renderRows(teams) {
    els.tableBody.innerHTML = "";
    teams.forEach((team) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><span class="rank-chip">${team.rank}</span></td>
        <td class="team-cell">${team.team_name}</td>
        <td>${team.w}</td>
        <td>${team.l}</td>
        <td>${team.win_pct_display}</td>
        <td>${team.diff > 0 ? `+${team.diff}` : team.diff}</td>
        <td>${team.gp}</td>
      `;
      els.tableBody.appendChild(row);
    });
  }

  async function loadLeague() {
    els.leagueTitle.textContent = leagueTitle || seasonLabel;
    els.emptyState.textContent = "Loading standings...";

    const endpoint = new URL("/api/standings", window.location.origin);
    endpoint.searchParams.set("season_id", seasonId);
    endpoint.searchParams.set("season_label", seasonLabel);
    endpoint.searchParams.set("hide_sunday", hideSunday ? "1" : "0");
    endpoint.searchParams.set("dedupe", dedupe ? "1" : "0");

    try {
      const response = await fetch(endpoint, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }
      const payload = await response.json();
      const league = (payload.leagues || []).find((item) => item.title === leagueTitle);
      if (!league) {
        throw new Error(`Could not find league "${leagueTitle}"`);
      }

      els.leagueTitle.textContent = league.title || leagueTitle;

      if (!league.teams || !league.teams.length) {
        els.emptyState.textContent = "No scored regular-season matches yet.";
        return;
      }

      els.emptyState.remove();
      renderRows(league.teams);
    } catch (error) {
      els.emptyState.textContent = `Could not load standings. ${error.message}`;
      els.emptyState.className = "empty-state is-error";
    }
  }

  loadLeague();
})();
