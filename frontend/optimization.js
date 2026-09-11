function optimizationLabel(profile) {
  return { fast: "Fast", reliable: "Reliable", all: "All" }[profile] || "Original";
}

function optimizationReason(candidate, policy, isPrimary) {
  if (isPrimary) {
    const strengths = [];
    if (policy.speed_weight >= 0.4) strengths.push("startup speed");
    if (policy.reliability_weight >= 0.4) strengths.push("reliability");
    if (policy.stability_weight >= 0.1) strengths.push("stability");
    return `Selected #${candidate.stream_id} as primary: highest weighted score${strengths.length ? ` with emphasis on ${strengths.join(" and ")}` : ""}.`;
  }
  return `Fallback candidate #${candidate.stream_id}, ranked below the primary by the same profile scoring.`;
}

function renderOptimizationPlan(plan) {
  const preview = $("optimization-preview");
  preview.hidden = false;
  const policy = plan.policy;
  const profile = optimizationLabel(plan.profile);
  $("optimization-summary").textContent = `${profile} profile · source playlist v${plan.version_number} · ${plan.channels.length} channels`;
  $("optimization-policy").innerHTML = `
    <div><strong>What drives the score</strong></div>
    <div class="policy-items">
      <span>Reliability ${Math.round(policy.reliability_weight * 100)}%</span>
      <span>Speed ${Math.round(policy.speed_weight * 100)}%</span>
      <span>P95 ${Math.round(policy.p95_weight * 100)}%</span>
      <span>Stability ${Math.round(policy.stability_weight * 100)}%</span>
      <span>Evidence ${Math.round(policy.evidence_weight * 100)}%</span>
      <span>Min success ${Math.round(policy.minimum_success_rate * 100)}%</span>
    </div>`;

  $("optimization-channels").innerHTML = plan.channels.length ? plan.channels.map((channel) => `
    <article class="optimization-channel">
      <div class="optimization-channel-head">
        <div><strong>${escapeHtml(channel.channel_name)}</strong><span class="meta"> · Channel #${channel.channel_id}</span></div>
        ${channel.primary_stream_id == null ? '<span class="badge muted">No eligible primary</span>' : `<span class="badge">Primary #${channel.primary_stream_id}</span>`}
      </div>
      ${channel.candidates.length ? `<div class="optimization-candidates">${channel.candidates.map((candidate) => {
        const primary = candidate.stream_id === channel.primary_stream_id;
        return `<div class="optimization-candidate ${primary ? "primary" : ""}">
          <div class="optimization-candidate-main">
            <strong>#${candidate.rank} · Stream ${candidate.stream_id}</strong>
            ${primary ? '<span class="badge small">Primary</span>' : '<span class="badge muted small">Fallback</span>'}
            <span class="optimization-score">${candidate.score.toFixed(1)}</span>
          </div>
          <div class="optimization-metrics">
            <span>Success ${formatPercent(candidate.success_rate)}</span>
            <span>Startup ${formatMs(candidate.median_first_frame_ms)}</span>
            <span>Stability ${formatPercent(candidate.stability_rate)}</span>
            <span>Tests ${candidate.total_tests}</span>
          </div>
          <div class="optimization-components meta">
            Reliability ${candidate.reliability_score.toFixed(1)} · Speed ${candidate.speed_score.toFixed(1)} · P95 ${candidate.p95_score.toFixed(1)} · Stability ${candidate.stability_score.toFixed(1)} · Evidence ${candidate.evidence_score.toFixed(1)}
          </div>
          <div class="optimization-reason">${escapeHtml(optimizationReason(candidate, policy, primary))}</div>
        </div>`;
      }).join("")}</div>` : '<div class="empty">No tested eligible streams meet this profile\'s requirements.</div>'}
    </article>`).join("") : '<div class="empty">No channels are present in this playlist version.</div>';
}

async function loadOptimizationPlan() {
  const playlist = selectedPlaylist();
  const profile = state.optimization;
  const preview = $("optimization-preview");
  if (!playlist || playlist.latest_version_id == null || !profile) {
    preview.hidden = true;
    return;
  }
  $("optimization-summary").textContent = "Loading optimization plan…";
  try {
    const plan = await getJson(
      `/api/source-playlists/${playlist.id}/optimization?profile=${encodeURIComponent(profile)}`,
    );
    renderOptimizationPlan(plan);
  } catch (error) {
    preview.hidden = false;
    $("optimization-summary").innerHTML = `<span class="error">Unable to load plan: ${escapeHtml(error.message)}</span>`;
    $("optimization-policy").innerHTML = "";
    $("optimization-channels").innerHTML = "";
  }
}

$("optimization").addEventListener("change", () => {
  window.setTimeout(loadOptimizationPlan, 0);
});
$("refresh-optimization").addEventListener("click", loadOptimizationPlan);
$("playlist").addEventListener("change", () => window.setTimeout(loadOptimizationPlan, 0));
$("refresh").addEventListener("click", () => window.setTimeout(loadOptimizationPlan, 0));
window.setTimeout(loadOptimizationPlan, 0);
