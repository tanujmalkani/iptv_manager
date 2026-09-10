const state = { channels: [], selectedId: null, playlists: [], playlistId: null, testRunId: null, polling: false };

const $ = (id) => document.getElementById(id);

function formatMs(value) { return value == null ? "—" : `${Math.round(value)} ms`; }
function formatPercent(value) { return value == null ? "—" : `${Math.round(value * 100)}%`; }
function formatMbps(value) { return value == null ? "—" : `${(value / 1_000_000).toFixed(2)} Mbps`; }
function formatDate(value) { return value ? new Date(value).toLocaleString() : "Never"; }

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function selectedPlaylist() { return state.playlists.find((item) => item.id === state.playlistId) || null; }

function renderPlaylists() {
  const select = $("playlist");
  select.innerHTML = `<option value="">Select playlist…</option>` + state.playlists.map((item) => {
    const version = item.latest_version_number == null ? "no completed version" : `v${item.latest_version_number}`;
    return `<option value="${item.id}">${escapeHtml(item.name)} · ${version}</option>`;
  }).join("");
  if (state.playlistId != null && state.playlists.some((item) => item.id === state.playlistId)) select.value = String(state.playlistId);
  const playlist = selectedPlaylist();
  const ready = playlist?.latest_version_id != null;
  $("test").disabled = !ready || state.polling;
  $("export").disabled = !ready || state.polling;
  $("playlist-summary").textContent = playlist
    ? `${playlist.entry_count} source entries · latest ${playlist.latest_version_number == null ? "—" : `v${playlist.latest_version_number}`}`
    : "Select a source playlist";
}

function renderChannels() {
  const query = $("filter").value.trim().toLowerCase();
  const items = state.channels.filter((item) => item.channel_name.toLowerCase().includes(query));
  $("channel-count").textContent = `${items.length} channel${items.length === 1 ? "" : "s"}`;
  $("channels").innerHTML = items.length ? items.map((item) => `
    <button class="channel ${item.channel_id === state.selectedId ? "selected" : ""}" data-id="${item.channel_id}">
      <div class="channel-title"><strong>${escapeHtml(item.channel_name)}</strong>${item.primary_stream_id != null ? '<span class="badge small">Primary</span>' : ""}</div>
      <span class="meta">${item.stream_count} streams · ${item.tested_stream_count} tested · best ${formatMs(item.best_first_frame_ms)} · ${formatPercent(item.best_success_rate)} best success</span>
    </button>`).join("") : `<div class="empty">No channels found in this playlist.</div>`;
  document.querySelectorAll(".channel").forEach((button) => button.addEventListener("click", () => selectChannel(Number(button.dataset.id))));
}

async function selectChannel(id) {
  state.selectedId = id;
  renderChannels();
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
  const startupValues = successful.map((item) => item.performance.median_first_frame_ms).filter((value) => value != null);
  const best = startupValues.length ? Math.min(...startupValues) : null;
  detail.innerHTML = `
    <div class="detail-header"><div><h2>${escapeHtml(channel.channel_name)}</h2><p class="meta">Channel #${channel.channel_id} · ${channel.streams.length} playable streams</p></div>
      ${channel.primary_stream_id != null ? `<span class="badge">Primary stream #${channel.primary_stream_id}</span>` : '<span class="badge muted">No tested primary</span>'}</div>
    <div class="metrics">
      <div class="metric"><div class="value">${channel.streams.length}</div><div class="label">Playable streams</div></div>
      <div class="metric"><div class="value">${tested.length}</div><div class="label">Tested streams</div></div>
      <div class="metric"><div class="value">${formatMs(best)}</div><div class="label">Best median startup</div></div>
      <div class="metric"><div class="value">${channel.primary_stream_id == null ? "—" : `#${channel.primary_stream_id}`}</div><div class="label">Recommended</div></div>
    </div>
    <div class="section-heading"><div><h3>Stream ranking</h3><p class="meta">Reliability is weighted more heavily than raw speed.</p></div><span class="meta">${tested.length} of ${channel.streams.length} tested</span></div>
    <div class="stream-list">${channel.streams.map(renderStream).join("")}</div>`;
}

function renderStream(item) {
  const p = item.performance;
  const reliability = p.total_tests ? Math.round(p.success_rate * 100) : 0;
  return `
    <article class="stream ${item.is_primary ? "primary" : ""}">
      <div class="stream-head"><div><strong>#${item.rank} · Stream ${item.stream_id}</strong> ${item.is_primary ? '<span class="badge">Primary</span>' : ""} ${p.total_tests === 0 ? '<span class="badge muted">Untested</span>' : ""}</div><div class="score"><strong>${item.score.toFixed(1)}</strong><span class="meta"> score</span></div></div>
      <div class="score-bar"><div style="width: ${Math.min(100, Math.max(0, item.score))}%"></div></div>
      <div class="stream-grid">
        <div><span class="meta">Tests</span><br>${p.total_tests}</div>
        <div><span class="meta">Success rate</span><br>${formatPercent(p.success_rate)}</div>
        <div><span class="meta">Median first frame</span><br>${formatMs(p.median_first_frame_ms)}</div>
        <div><span class="meta">P95 first frame</span><br>${formatMs(p.p95_first_frame_ms)}</div>
        <div><span class="meta">Median throughput</span><br>${formatMbps(p.median_throughput_bps)}</div>
        <div><span class="meta">Average throughput</span><br>${formatMbps(p.average_throughput_bps)}</div>
        <div><span class="meta">Avg FPS</span><br>${p.average_fps == null ? "—" : p.average_fps.toFixed(1)}</div>
        <div><span class="meta">Stability</span><br>${formatPercent(p.stability_rate)}</div>
        <div><span class="meta">Median playback</span><br>${formatMs(p.median_playback_duration_ms)}</div>
        <div><span class="meta">Last tested</span><br>${formatDate(p.last_tested_at)}</div>
      </div>
      <div class="stream-foot meta">${p.total_tests ? `${reliability}% successful observations · ${p.stable_tests} stable runs` : "No historical test observations yet"}</div>
    </article>`;
}

async function loadPlaylists() {
  try {
    state.playlists = await getJson("/api/source-playlists");
    if (state.playlistId == null) {
      const first = state.playlists.find((item) => item.latest_version_id != null);
      state.playlistId = first ? first.id : null;
    }
    renderPlaylists();
  } catch (error) { $("status").innerHTML = `<span class="error">Playlist API error: ${escapeHtml(error.message)}</span>`; }
}

async function loadChannels() {
  try {
    const url = state.playlistId == null ? "/api/channels" : `/api/channels?source_playlist_id=${encodeURIComponent(state.playlistId)}`;
    state.channels = await getJson(url);
    if (state.selectedId != null && !state.channels.some((item) => item.channel_id === state.selectedId)) {
      state.selectedId = null; $("empty").hidden = false; $("channel-detail").hidden = true;
    }
    renderChannels();
    if (state.selectedId != null && state.channels.some((item) => item.channel_id === state.selectedId)) await selectChannel(state.selectedId);
  } catch (error) { $("status").innerHTML = `<span class="error">Channel API error: ${escapeHtml(error.message)}</span>`; }
}

function renderTestProgress(run) {
  const progress = $("test-progress"); progress.hidden = false;
  const total = run.total_streams || 0; const completed = run.completed_streams || 0;
  const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  $("test-progress-count").textContent = `${completed} / ${total}`;
  $("test-progress-bar").style.width = `${percent}%`;
  $("test-progress-label").textContent = run.status === "completed"
    ? `Test complete · ${run.successful_streams} successful · ${run.failed_streams} failed`
    : run.status === "failed" ? "Test failed" : "Testing streams…";
}

async function pollTestRun(runId) {
  state.polling = true; renderPlaylists();
  try {
    while (true) {
      const run = await getJson(`/api/stream-tests/${runId}`); renderTestProgress(run);
      if (["completed", "failed", "cancelled"].includes(run.status)) {
        state.polling = false; renderPlaylists(); await loadChannels();
        $("status").textContent = `Stream test ${run.status}: ${run.successful_streams} successful, ${run.failed_streams} failed`;
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (error) { state.polling = false; renderPlaylists(); $("status").innerHTML = `<span class="error">Test status error: ${escapeHtml(error.message)}</span>`; }
}

async function startTest() {
  const playlist = selectedPlaylist(); if (!playlist || playlist.latest_version_id == null || state.polling) return;
  $("status").textContent = `Starting stream test for ${playlist.name}…`;
  try {
    const response = await fetch(`/api/stream-tests?source_playlist_id=${encodeURIComponent(state.playlistId)}`, { method: "POST" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const run = await response.json(); state.testRunId = run.test_run_id; renderTestProgress(run); await pollTestRun(state.testRunId);
  } catch (error) { $("status").innerHTML = `<span class="error">Test start failed: ${escapeHtml(error.message)}</span>`; }
}

async function exportPlaylist() {
  if (state.playlistId == null || state.polling) return;
  const playlist = selectedPlaylist(); if (!playlist || playlist.latest_version_id == null) return;
  $("status").textContent = "Preparing optimized playlist…";
  try {
    const response = await fetch(`/api/source-playlists/${state.playlistId}/optimized.m3u`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob(); const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `iptv-manager-optimized-v${playlist.latest_version_number}.m3u`;
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename;
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); $("status").textContent = `Exported ${filename}`;
  } catch (error) { $("status").innerHTML = `<span class="error">Export failed: ${escapeHtml(error.message)}</span>`; }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

$("refresh").addEventListener("click", async () => { await loadPlaylists(); await loadChannels(); });
$("playlist").addEventListener("change", async (event) => {
  state.playlistId = Number(event.target.value) || null; state.selectedId = null;
  $("empty").hidden = false; $("channel-detail").hidden = true; renderPlaylists(); await loadChannels();
});
$("test").addEventListener("click", startTest); $("export").addEventListener("click", exportPlaylist); $("filter").addEventListener("input", renderChannels);
Promise.all([loadPlaylists(), loadChannels()]);
