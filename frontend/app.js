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