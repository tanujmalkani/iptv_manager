(() => {
  function number(value) { return new Intl.NumberFormat().format(value || 0); }

  function renderOverview() {
    const target = $("overview-content");
    if (!target) return;
    const playlist = selectedPlaylist();
    if (!playlist) {
      target.innerHTML = `<section class="panel empty-state-card"><div class="empty">Select or import a playlist to see its health dashboard.</div></section>`;
      return;
    }

    const channels = state.channels || [];
    const streamCount = channels.reduce((sum, item) => sum + (item.stream_count || 0), 0);
    const testedCount = channels.reduce((sum, item) => sum + (item.tested_stream_count || 0), 0);
    const successfulChannels = channels.filter((item) => item.best_success_rate != null);
    const successRate = successfulChannels.length
      ? successfulChannels.reduce((sum, item) => sum + item.best_success_rate, 0) / successfulChannels.length
      : null;
    const startup = channels.map((item) => item.best_first_frame_ms).filter((value) => value != null);
    const median = startup.length ? startup.slice().sort((a, b) => a - b)[Math.floor(startup.length / 2)] : null;
    const primaryCount = channels.filter((item) => item.primary_stream_id != null).length;
    const coverage = streamCount ? testedCount / streamCount : 0;

    target.innerHTML = `
      <div class="hero-card panel">
        <div>
          <p class="eyebrow">Current source</p>
          <h3>${escapeHtml(playlist.name)}</h3>
          <p class="meta">Latest completed version ${playlist.latest_version_number == null ? "—" : `v${playlist.latest_version_number}`} · ${number(playlist.entry_count)} source entries</p>
        </div>
        <button type="button" class="secondary-button" id="overview-go-channels">Inspect channels</button>
      </div>

      <div class="overview-metrics">
        <div class="metric"><div class="value">${number(channels.length)}</div><div class="label">Channels</div></div>
        <div class="metric"><div class="value">${number(streamCount)}</div><div class="label">Playable streams</div></div>
        <div class="metric"><div class="value">${number(testedCount)}</div><div class="label">Tested streams</div></div>
        <div class="metric"><div class="value">${successRate == null ? "—" : formatPercent(successRate)}</div><div class="label">Best-stream success</div></div>
      </div>

      <div class="overview-grid">
        <section class="panel overview-section">
          <div class="panel-title"><div><h3>Performance</h3><p class="meta">Current best observed channel-level measurements.</p></div></div>
          <div class="overview-stat-list">
            <div><span>Best median startup</span><strong>${formatMs(startup.length ? Math.min(...startup) : null)}</strong></div>
            <div><span>Median channel best startup</span><strong>${formatMs(median)}</strong></div>
            <div><span>Test coverage</span><strong>${Math.round(coverage * 100)}%</strong></div>
            <div><span>Channels with primary</span><strong>${number(primaryCount)}</strong></div>
          </div>
        </section>

        <section class="panel overview-section">
          <div class="panel-title"><div><h3>Workflow</h3><p class="meta">Jump directly to the next useful step.</p></div></div>
          <div class="workflow-links">
            <button type="button" data-page-link="testing"><strong>Testing</strong><span class="meta">Run a Quick or Deep campaign</span></button>
            <button type="button" data-page-link="export"><strong>Optimization & Export</strong><span class="meta">Build a profile and validate your M3U</span></button>
            <button type="button" data-page-link="import"><strong>Import</strong><span class="meta">Create a new source version</span></button>
          </div>
        </section>
      </div>`;

    $("overview-go-channels")?.addEventListener("click", () => window.showPage?.("channels"));
    target.querySelectorAll("[data-page-link]").forEach((button) => {
      button.addEventListener("click", () => window.showPage?.(button.dataset.pageLink));
    });
  }

  window.renderOverview = renderOverview;
  window.addEventListener("iptv:pagechange", (event) => {
    if (event.detail?.page === "overview") renderOverview();
  });
  window.addEventListener("iptv:datachange", renderOverview);
  window.setTimeout(renderOverview, 0);
})();
