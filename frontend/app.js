const state = { channels: [], selectedId: null };

const $ = (id) => document.getElementById(id);

function formatMs(value) {
  return value == null ? "—" : `${Math.round(value)} ms`;
}

function formatPercent(value) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "Never";
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function renderChannels() {
  const query = $("filter").value.trim().toLowerCase();
  const items = state.channels.filter((item) => item.channel_name.toLowerCase().includes(query));
  $("channels").innerHTML = items.length
    ? items.map((item) => `
      <button class="channel" data-id="${item.channel_id}">
        <strong>${escapeHtml(item.channel_name)}</strong>
        <span class="meta">${item.stream_count} streams · ${item.tested_stream_count} tested · ${formatMs(item.best_first_frame_ms)}</span>
      </button>`).join("")
    : `<div class="empty">No channels found.</div>`;

  document.querySelectorAll(".channel").forEach((button) => {
    button.addEventListener("click", () => selectChannel(Number(button.dataset.id)));
  });
}

async function selectChannel(id) {
  state.selectedId = id;
  $("status").textContent = "Loading channel performance…";
  try {
    const channel = await getJson(`/api/channels/${id}`);
    renderDetail(channel);
    $("status").textContent = `Loaded ${channel.channel_name}`;
  } catch (error) {
    $("status").innerHTML = `<span class="error">Unable to load channel: ${escapeHtml(error.message)}</span>`;
  }
}

function renderDetail(channel) {
  $("empty").hidden = true;
  const detail = $("channel-detail");
  detail.hidden = false;
  const tested = channel.streams.filter((item) => item.performance.total_tests > 0);
  const successful = channel.streams.filter((item) => item.performance.successful_tests > 0);
  const startupValues = successful
    .map((item) => item.performance.median_first_frame_ms)
    .filter((value) => value != null);
  const best = startupValues.length ? Math.min(...startupValues) : null;

  detail.innerHTML = `
    <div class="detail-header">
      <div><h2>${escapeHtml(channel.channel_name)}</h2><p class="meta">Channel #${channel.channel_id}</p></div>
      ${channel.primary_stream_id != null ? `<span class="badge">Primary stream #${channel.primary_stream_id}</span>` : "<span class="meta">No tested primary</span>"}
    </div>
    <div class="metrics">
      <div class="metric"><div class="value">${channel.streams.length}</div><div class="label">Playable streams</div></div>
      <div class="metric"><div class="value">${tested.length}</div><div class="label">Tested streams</div></div>
      <div class="metric"><div class="value">${formatMs(best)}</div><div class="label">Best median startup</div></div>
      <div class="metric"><div class="value">${channel.primary_stream_id == null ? "—" : `#${channel.primary_stream_id}`}</div><div class="label">Recommended</div></div>
    </div>
    ${channel.streams.map(renderStream).join("")}
  `;
}

function renderStream(item) {
  const p = item.performance;
  return `
    <article class="stream ${item.is_primary ? "primary" : ""}">
      <div class="stream-head">
        <div><strong>#${item.rank} · Stream ${item.stream_id}</strong> ${item.is_primary ? '<span class="badge">Primary</span>' : ""}</div>
        <strong>Score ${item.score.toFixed(1)}</strong>
      </div>
      <div class="stream-grid">
        <div><span class="meta">Tests</span><br>${p.total_tests}</div>
        <div><span class="meta">Success</span><br>${formatPercent(p.success_rate)}</div>
        <div><span class="meta">Median first frame</span><br>${formatMs(p.median_first_frame_ms)}</div>
        <div><span class="meta">P95 first frame</span><br>${formatMs(p.p95_first_frame_ms)}</div>
        <div><span class="meta">Avg FPS</span><br>${p.average_fps == null ? "—" : p.average_fps.toFixed(1)}</div>
        <div><span class="meta">Stability</span><br>${formatPercent(p.stability_rate)}</div>
        <div><span class="meta">Median playback</span><br>${formatMs(p.median_playback_duration_ms)}</div>
        <div><span class="meta">Last tested</span><br>${formatDate(p.last_tested_at)}</div>
      </div>
    </article>`;
}

async function loadChannels() {
  $("status").textContent = "Loading channels…";
  try {
    state.channels = await getJson("/api/channels");
    renderChannels();
    $("status").textContent = `${state.channels.length} channels loaded`;
    if (state.selectedId != null && state.channels.some((item) => item.channel_id === state.selectedId)) {
      await selectChannel(state.selectedId);
    }
  } catch (error) {
    $("status").innerHTML = `<span class="error">API error: ${escapeHtml(error.message)}</span>`;
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

$("refresh").addEventListener("click", loadChannels);
$("filter").addEventListener("input", renderChannels);
loadChannels();
