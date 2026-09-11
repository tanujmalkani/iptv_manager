(() => {
  let filterMode = "all";
  let sortMode = "name";

  function health(item) {
    if (!item.tested_stream_count) return ["Untested", "stale"];
    const rate = item.best_success_rate == null ? 0 : item.best_success_rate;
    if (rate < 0.5) return ["Failing", "failing"];
    if (rate < 0.8) return ["Degraded", "degraded"];
    return ["Healthy", "healthy"];
  }

  function ensureControls() {
    const panelTitle = document.querySelector(".channel-browser .panel-title");
    if (!panelTitle || document.getElementById("channel-filter-mode")) return;
    const controls = document.createElement("div");
    controls.className = "channel-filters";
    controls.innerHTML = `
      <select id="channel-filter-mode" aria-label="Channel health filter">
        <option value="all">All health states</option>
        <option value="healthy">Healthy</option>
        <option value="degraded">Degraded</option>
        <option value="failing">Failing</option>
        <option value="stale">Untested</option>
      </select>
      <select id="channel-sort-mode" aria-label="Channel sort order">
        <option value="name">Name</option>
        <option value="startup">Best startup</option>
        <option value="success">Best success</option>
        <option value="streams">Most streams</option>
      </select>`;
    panelTitle.appendChild(controls);
    controls.querySelector("#channel-filter-mode").addEventListener("change", (event) => {
      filterMode = event.target.value;
      renderChannels();
    });
    controls.querySelector("#channel-sort-mode").addEventListener("change", (event) => {
      sortMode = event.target.value;
      renderChannels();
    });
  }

  window.renderChannels = function renderChannelsEnhanced() {
    ensureControls();
    const query = $("filter").value.trim().toLowerCase();
    let items = state.channels.filter((item) => item.channel_name.toLowerCase().includes(query));
    items = items.filter((item) => filterMode === "all" || health(item)[1] === filterMode);
    items.sort((a, b) => {
      if (sortMode === "startup") return (a.best_first_frame_ms ?? Number.POSITIVE_INFINITY) - (b.best_first_frame_ms ?? Number.POSITIVE_INFINITY);
      if (sortMode === "success") return (b.best_success_rate ?? -1) - (a.best_success_rate ?? -1);
      if (sortMode === "streams") return (b.stream_count ?? 0) - (a.stream_count ?? 0);
      return a.channel_name.localeCompare(b.channel_name);
    });
    $("channel-count").textContent = `${items.length} channel${items.length === 1 ? "" : "s"}`;
    $("channel-browser-summary").textContent = `${items.length} shown · ${state.channels.length} total`;
    $("channels").innerHTML = items.length ? items.map((item) => {
      const [label, tone] = health(item);
      return `
        <button class="channel ${item.channel_id === state.selectedId ? "selected" : ""}" data-id="${item.channel_id}">
          <div class="channel-title"><strong>${escapeHtml(item.channel_name)}</strong>${item.primary_stream_id != null ? '<span class="badge small">Primary</span>' : ""}</div>
          <span class="meta">${item.stream_count} streams · ${item.tested_stream_count} tested · best ${formatMs(item.best_first_frame_ms)} · ${formatPercent(item.best_success_rate)} best success</span>
          <span class="channel-status-line"><span class="status-pill ${tone}">${label}</span></span>
        </button>`;
    }).join("") : `<div class="empty">No channels match the current filters.</div>`;
    document.querySelectorAll(".channel").forEach((button) => button.addEventListener("click", () => selectChannel(Number(button.dataset.id))));
  };

  const originalRenderDetail = window.renderDetail;
  window.renderDetail = function renderDetailEnhanced(channel) {
    originalRenderDetail(channel);
    const stale = channel.streams.filter((item) => item.performance.last_tested_at).some((item) =>
      Date.now() - new Date(item.performance.last_tested_at).getTime() > 7 * 24 * 60 * 60 * 1000
    );
    if (stale) {
      const header = document.querySelector("#channel-detail .detail-header");
      header?.insertAdjacentHTML("beforeend", '<span class="status-pill degraded">Some observations are older than 7 days</span>');
    }
  };

  setTimeout(ensureControls, 0);
})();
