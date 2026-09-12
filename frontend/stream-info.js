function formatBitrate(value) {
  if (value == null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} Mbps`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} Kbps`;
  return `${Math.round(value)} bps`;
}

function streamTechnicalMarkup(info) {
  if (!info) return '<div class="stream-info-empty">No stream metadata available.</div>';
  const resolution = info.resolution || "—";
  const bitrate = info.bitrate_bps != null
    ? formatBitrate(info.bitrate_bps)
    : info.average_bitrate_bps != null
      ? formatBitrate(info.average_bitrate_bps)
      : "—";
  const bitrateLabel = info.bitrate_bps != null ? "Advertised bitrate" : "Average bitrate";
  const fps = info.frame_rate != null ? `${Number(info.frame_rate).toFixed(2)} fps` : "—";
  const codec = info.codecs || info.observed_codec || "—";
  const audio = info.audio_present == null ? "—" : info.audio_present ? "Yes" : "No";
  return `
    <div class="stream-info-grid">
      <div><span class="meta">Resolution</span><br>${escapeHtml(resolution)}</div>
      <div><span class="meta">${bitrateLabel}</span><br>${escapeHtml(bitrate)}</div>
      <div><span class="meta">Variant FPS</span><br>${escapeHtml(fps)}</div>
      <div><span class="meta">Codec</span><br>${escapeHtml(codec)}</div>
      <div><span class="meta">Audio</span><br>${audio}</div>
      <div><span class="meta">Stream type</span><br>${escapeHtml(info.stream_kind || "—")}</div>
    </div>`;
}

function streamTestMarkup(performance) {
  return `
    <div class="stream-test-grid">
      <div><span class="meta">Tests</span><br>${performance.total_tests}</div>
      <div><span class="meta">Success</span><br>${formatPercent(performance.success_rate)}</div>
      <div><span class="meta">Median startup</span><br>${formatMs(performance.median_first_frame_ms)}</div>
      <div><span class="meta">P95 startup</span><br>${formatMs(performance.p95_first_frame_ms)}</div>
      <div><span class="meta">Median throughput</span><br>${formatMbps(performance.median_throughput_bps)}</div>
      <div><span class="meta">Avg throughput</span><br>${formatMbps(performance.average_throughput_bps)}</div>
      <div><span class="meta">Observed FPS</span><br>${performance.average_fps == null ? "—" : performance.average_fps.toFixed(1)}</div>
      <div><span class="meta">Stability</span><br>${formatPercent(performance.stability_rate)}</div>
      <div><span class="meta">Playback</span><br>${formatMs(performance.median_playback_duration_ms)}</div>
      <div><span class="meta">Last tested</span><br>${formatDate(performance.last_tested_at)}</div>
    </div>`;
}

function enhanceChannelStreamCards(channel) {
  document.querySelectorAll("#channel-detail .stream").forEach((card, index) => {
    const item = channel.streams[index];
    if (!item) return;
    const details = document.createElement("div");
    details.className = "stream-details";
    details.hidden = true;
    details.innerHTML = `
      <div class="score-bar"><div style="width: ${Math.min(100, Math.max(0, item.score))}%"></div></div>
      <div class="stream-info-panels">
        <section class="stream-info-panel">
          <div class="stream-info-title"><strong>Stream information</strong><span class="meta">${escapeHtml(item.stream_info.protocol || "Unknown protocol")}</span></div>
          ${streamTechnicalMarkup(item.stream_info)}
        </section>
        <section class="stream-info-panel stream-test-panel">
          <div class="stream-info-title"><strong>Test data</strong><span class="meta">${item.performance.total_tests ? "Historical observations" : "No test history"}</span></div>
          ${streamTestMarkup(item.performance)}
        </section>
        <div class="stream-foot meta">${item.performance.total_tests ? `${item.performance.successful_tests} successful · ${item.performance.stable_tests} stable runs` : "No historical test observations yet"}</div>
      </div>`;

    const protocol = item.stream_info?.protocol ? ` · ${item.stream_info.protocol}` : "";
    const summary = document.createElement("button");
    summary.type = "button";
    summary.className = "stream-summary-toggle";
    summary.setAttribute("aria-expanded", "false");
    summary.innerHTML = `
      <span class="stream-summary-main">
        <strong>#${item.rank} · Stream ${item.stream_id}</strong>
        ${item.is_primary ? '<span class="badge">Primary</span>' : ""}
      </span>
      <span class="stream-summary-metrics">
        <span>${escapeHtml(item.stream_info?.resolution || "Unknown res")}</span>
        <span>${formatMs(item.performance.median_first_frame_ms)}</span>
        <span>${formatPercent(item.performance.success_rate)} success</span>
        <span>${item.score.toFixed(1)} score</span>
        <span class="stream-summary-protocol">${escapeHtml(protocol)}</span>
      </span>
      <span class="stream-summary-chevron" aria-hidden="true">⌄</span>`;

    card.replaceChildren(summary, details);
    card.classList.add("stream-collapsible");
    summary.addEventListener("click", () => {
      const expanded = !details.hidden;
      details.hidden = expanded;
      summary.setAttribute("aria-expanded", String(!expanded));
      card.classList.toggle("expanded", !expanded);
    });
  });
}

const originalRenderDetailWithStreamInfo = window.renderDetail;
window.renderDetail = function renderDetailWithStreamInfo(channel) {
  originalRenderDetailWithStreamInfo(channel);
  enhanceChannelStreamCards(channel);
};

const originalRenderOptimizationPlanWithStreamInfo = window.renderOptimizationPlan;
window.renderOptimizationPlan = function renderOptimizationPlanWithStreamInfo(plan) {
  originalRenderOptimizationPlanWithStreamInfo(plan);
  plan.channels.forEach((channel) => {
    const section = [...document.querySelectorAll("#optimization-channels .optimization-channel")]
      .find((node) => node.textContent.includes(`Channel #${channel.channel_id}`));
    if (!section) return;
    const candidates = [...section.querySelectorAll(".optimization-candidate")];
    channel.candidates.forEach((candidate, index) => {
      const card = candidates[index];
      if (!card) return;
      const old = card.querySelector(".stream-info-panel");
      old?.remove();
      const panel = document.createElement("section");
      panel.className = "stream-info-panel optimization-stream-info";
      panel.innerHTML = `
        <div class="stream-info-title"><strong>Stream information</strong><span class="meta">${escapeHtml(candidate.stream_info.protocol || "Unknown protocol")}</span></div>
        ${streamTechnicalMarkup(candidate.stream_info)}`;
      card.querySelector(".optimization-components")?.insertAdjacentElement("beforebegin", panel);
    });
  });
};

const originalRenderExportPreviewWithStreamInfo = window.renderExportPreview;
window.renderExportPreview = function renderExportPreviewWithStreamInfo(preview) {
  originalRenderExportPreviewWithStreamInfo(preview);
  document.querySelector("#export-preview .export-selection-info")?.remove();
  if (!preview.selections?.length) return;
  const section = document.createElement("section");
  section.className = "export-selection-info";
  section.innerHTML = `
    <div class="section-heading">
      <div><h3>Exported stream details</h3><p class="meta">Technical metadata and historical test evidence for the exact stream selected for each channel.</p></div>
      <span class="meta">${preview.selections.length} selections</span>
    </div>
    <div class="export-selection-list">
      ${preview.selections.map((selection) => `
        <article class="export-selection-card">
          <div class="stream-head">
            <div><strong>${escapeHtml(selection.channel_name)}</strong><span class="meta"> · Stream #${selection.stream_info.stream_id}</span></div>
            ${selection.optimized ? '<span class="badge">Optimized</span>' : selection.fallback ? '<span class="badge muted">Fallback</span>' : '<span class="badge muted">Source</span>'}
          </div>
          <div class="stream-info-panel">
            <div class="stream-info-title"><strong>Stream information</strong><span class="meta">${escapeHtml(selection.stream_info.protocol || "Unknown protocol")}</span></div>
            ${streamTechnicalMarkup(selection.stream_info)}
          </div>
          <div class="stream-info-panel stream-test-panel">
            <div class="stream-info-title"><strong>Test data</strong></div>
            ${streamTestMarkup(selection.performance)}
          </div>
        </article>`).join("")}
    </div>`;
  $("export-preview-warnings").insertAdjacentElement("afterend", section);
};
