const state = {
  channels: [],
  selectedId: null,
  playlists: [],
  playlistId: null,
  profiles: [],
  profileId: null,
  profileEntries: [],
  optimization: "fast",
  testRunId: null,
  polling: false,
  testType: null,
};

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
function selectedProfile() { return state.profiles.find((item) => item.id === state.profileId) || null; }

function renderPlaylists() {
  const select = $("playlist");
  select.innerHTML = `<option value="">Select playlist…</option>` + state.playlists.map((item) => {
    const version = item.latest_version_number == null ? "no completed version" : `v${item.latest_version_number}`;
    return `<option value="${item.id}">${escapeHtml(item.name)} · ${version}</option>`;
  }).join("");
  if (state.playlistId != null) select.value = String(state.playlistId);

  const playlist = selectedPlaylist();
  const ready = playlist?.latest_version_id != null;
  $("test").disabled = !ready || state.polling;
  $("deep-test").disabled = !ready || state.polling;
  $("export").disabled = !ready || state.polling;
  $("save-profile").disabled = !ready || state.polling;
  $("playlist-summary").textContent = playlist
    ? `${playlist.entry_count} source entries · latest ${playlist.latest_version_number == null ? "—" : `v${playlist.latest_version_number}`}`
    : "Select a source playlist";
  if (window.renderTestRecommendations) window.renderTestRecommendations();
}

function renderProfiles() {
  const select = $("profile");
  select.innerHTML = `<option value="">Input playlist</option>` + state.profiles.map((item) =>
    `<option value="${item.id}">${escapeHtml(item.name)} · ${item.entries.length} channels</option>`
  ).join("");
  if (state.profileId != null) select.value = String(state.profileId);
  renderProfileEditor();
}

function renderProfileEditor() {
  const editor = $("profile-editor");
  editor.hidden = state.playlistId == null;
  if (editor.hidden) return;
  if (state.profileId != null) {
    const profile = selectedProfile();
    $("profile-name").value = profile?.name || "";
  }

  const channelById = new Map(state.channels.map((item) => [item.channel_id, item]));
  const rows = state.profileEntries.filter((item) => channelById.has(item.channel_id));
  $("profile-channels").innerHTML = rows.length ? rows.map((item, index) => {
    const channel = channelById.get(item.channel_id);
    const selection = item.selected_stream_id == null
      ? "Auto-select stream"
      : `Stream #${item.selected_stream_id} selected`;
    return `<div class="profile-row" data-id="${item.channel_id}">
      <input type="checkbox" class="profile-enabled" ${item.enabled ? "checked" : ""} aria-label="Include ${escapeHtml(channel.channel_name)}">
      <div><strong>${index + 1}. ${escapeHtml(channel.channel_name)}</strong><div class="profile-row-selection">${selection}</div></div>
      <div class="profile-row-actions">
        <button class="profile-up" ${index === 0 ? "disabled" : ""}>↑</button>
        <button class="profile-down" ${index === rows.length - 1 ? "disabled" : ""}>↓</button>
      </div>
    </div>`;
  }).join("") : `<div class="empty">No channels available.</div>`;

  document.querySelectorAll(".profile-row").forEach((row) => {
    const id = Number(row.dataset.id);
    row.querySelector(".profile-enabled").addEventListener("change", (event) => {
      const entry = state.profileEntries.find((item) => item.channel_id === id);
      if (entry) entry.enabled = event.target.checked;
    });
    row.querySelector(".profile-up").addEventListener("click", () => moveProfileEntry(id, -1));
    row.querySelector(".profile-down").addEventListener("click", () => moveProfileEntry(id, 1));
  });
}

function moveProfileEntry(channelId, delta) {
  const index = state.profileEntries.findIndex((item) => item.channel_id === channelId);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= state.profileEntries.length) return;
  [state.profileEntries[index], state.profileEntries[target]] = [state.profileEntries[target], state.profileEntries[index]];
  state.profileEntries.forEach((item, position) => { item.position = position; });
  renderProfileEditor();
}

function startNewProfile() {
  state.profileId = null;
  state.profileEntries = state.channels.map((item, position) => ({
    channel_id: item.channel_id,
    position,
    enabled: true,
    group_name: null,
    selected_stream_id: null,
  }));
  $("profile-name").value = "";
  $("profile").value = "";
  renderProfileEditor();
}

async function loadProfiles() {
  if (state.playlistId == null) {
    state.profiles = [];
    state.profileId = null;
    renderProfiles();
    return;
  }
  state.profiles = await getJson(`/api/playlist-profiles?source_playlist_id=${encodeURIComponent(state.playlistId)}`);
  if (state.profileId != null && !state.profiles.some((item) => item.id === state.profileId)) state.profileId = null;
  renderProfiles();
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
    <div class="section-heading"><div><h3>Stream ranking</h3><p class="meta">Use Fast, Reliable, or All when exporting.</p></div><span class="meta">${tested.length} of ${channel.streams.length} tested</span></div>
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
    if (state.profileId == null) startNewProfile();
    else {
      const profile = selectedProfile();
      state.profileEntries = profile ? profile.entries.map((item) => ({ ...item })) : [];
      renderProfileEditor();
    }
  } catch (error) { $("status").innerHTML = `<span class="error">Channel API error: ${escapeHtml(error.message)}</span>`; }
}

function renderTestProgress(run) {
  const progress = $("test-progress"); progress.hidden = false;
  const total = run.total_streams || 0; const completed = run.completed_streams || 0;
  const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  $("test-progress-count").textContent = `${completed} / ${total}`;
  $("test-progress-bar").style.width = `${percent}%`;
  const typeLabel = state.testType === "deep" ? "Deep test" : "Quick test";
  $("test-progress-label").textContent = run.status === "completed"
    ? `${typeLabel} complete · ${run.successful_streams} successful · ${run.failed_streams} failed`
    : run.status === "failed" ? `${typeLabel} failed` : `${typeLabel} running…`;
}

async function pollTestRun(runId) {
  state.polling = true; renderPlaylists();
  try {
    while (true) {
      const run = await getJson(`/api/stream-tests/${runId}`); renderTestProgress(run);
      if (["completed", "failed", "cancelled"].includes(run.status)) {
        state.polling = false; renderPlaylists(); await loadChannels();
        $("status").textContent = `${state.testType === "deep" ? "Deep" : "Quick"} test ${run.status}: ${run.successful_streams} successful, ${run.failed_streams} failed`;
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (error) { state.polling = false; renderPlaylists(); $("status").innerHTML = `<span class="error">Test status error: ${escapeHtml(error.message)}</span>`; }
}

async function startTest(testType) {
  const playlist = selectedPlaylist();
  if (!playlist || playlist.latest_version_id == null || state.polling) return;
  state.testType = testType;
  const label = testType === "deep" ? "Deep test" : "Quick test";
  $("status").textContent = `Starting ${label.toLowerCase()} for ${playlist.name}…`;
  try {
    const response = await fetch(`/api/stream-tests?source_playlist_id=${encodeURIComponent(state.playlistId)}&test_type=${encodeURIComponent(testType)}`, { method: "POST" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const run = await response.json();
    state.testRunId = run.test_run_id;
    renderTestProgress(run);
    await pollTestRun(state.testRunId);
  } catch (error) { state.polling = false; renderPlaylists(); $("status").innerHTML = `<span class="error">Test start failed: ${escapeHtml(error.message)}</span>`; }
}

async function saveProfile() {
  const playlist = selectedPlaylist();
  const name = $("profile-name").value.trim();
  if (!playlist || !name || state.polling) return;
  const payload = {
    name,
    source_playlist_id: state.playlistId,
    description: null,
    entries: state.profileEntries.map((entry, position) => ({
      channel_id: entry.channel_id,
      position,
      enabled: entry.enabled,
      group_name: entry.group_name || null,
      selected_stream_id: entry.selected_stream_id || null,
    })),
  };
  try {
    const url = state.profileId == null ? "/api/playlist-profiles" : `/api/playlist-profiles/${state.profileId}`;
    const response = await fetch(url, {
      method: state.profileId == null ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    const profile = await response.json();
    state.profileId = profile.id;
    await loadProfiles();
    $("profile").value = String(profile.id);
    $("status").textContent = `Saved playlist profile ${profile.name}`;
  } catch (error) { $("status").innerHTML = `<span class="error">Profile save failed: ${escapeHtml(error.message)}</span>`; }
}

async function exportPlaylist() {
  if (state.playlistId == null || state.polling) return;
  const playlist = selectedPlaylist(); if (!playlist || playlist.latest_version_id == null) return;
  $("status").textContent = "Preparing playlist…";
  try {
    const params = new URLSearchParams();
    if (state.optimization) params.set("optimization_profile", state.optimization);
    if (state.profileId != null) params.set("playlist_profile_id", state.profileId);
    const query = params.toString();
    const response = await fetch(`/api/source-playlists/${state.playlistId}/export.m3u${query ? `?${query}` : ""}`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob(); const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const suffix = state.optimization || "original";
    const filename = match ? match[1] : `iptv-manager-${suffix}-v${playlist.latest_version_number}.m3u`;
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename;
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); $("status").textContent = `Exported ${filename}`;
  } catch (error) { $("status").innerHTML = `<span class="error">Export failed: ${escapeHtml(error.message)}</span>`; }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

$("refresh").addEventListener("click", async () => { await loadPlaylists(); await loadChannels(); await loadProfiles(); });
$("playlist").addEventListener("change", async (event) => {
  state.playlistId = Number(event.target.value) || null; state.selectedId = null; state.profileId = null;
  $("empty").hidden = false; $("channel-detail").hidden = true; renderPlaylists(); await loadChannels(); await loadProfiles();
});
$("profile").addEventListener("change", async (event) => {
  state.profileId = Number(event.target.value) || null;
  if (state.profileId == null) startNewProfile();
  else {
    const profile = await getJson(`/api/playlist-profiles/${state.profileId}`);
    state.profileEntries = profile.entries.map((item) => ({ ...item }));
    renderProfileEditor();
  }
});
$("optimization").addEventListener("change", (event) => { state.optimization = event.target.value; });
$("save-profile").addEventListener("click", saveProfile);
$("test").addEventListener("click", () => startTest("quick"));
$("deep-test").addEventListener("click", () => startTest("deep"));
$("export").addEventListener("click", exportPlaylist);
$("filter").addEventListener("input", renderChannels);
Promise.all([loadPlaylists(), loadChannels()]).then(loadProfiles);