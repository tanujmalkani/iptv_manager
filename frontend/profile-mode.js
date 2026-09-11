const PROFILE_STREAM_MODES = new Set(["source", "fast", "reliable", "all"]);

function applySavedProfileMode() {
  if (state.profileId == null) return;
  const profile = selectedProfile();
  if (!profile || !PROFILE_STREAM_MODES.has(profile.stream_mode)) return;
  state.optimization = profile.stream_mode;
  $("optimization").value = profile.stream_mode;
}

async function saveProfileWithMode() {
  const playlist = selectedPlaylist();
  const name = $("profile-name").value.trim();
  if (!playlist || !name || state.polling) return;

  const payload = {
    name,
    source_playlist_id: state.playlistId,
    description: null,
    stream_mode: state.optimization || "source",
    entries: state.profileEntries.map((entry, position) => ({
      channel_id: entry.channel_id,
      position,
      enabled: entry.enabled,
      group_name: entry.group_name || null,
      selected_stream_id: entry.selected_stream_id || null,
    })),
  };

  try {
    const url = state.profileId == null
      ? "/api/playlist-profiles"
      : `/api/playlist-profiles/${state.profileId}`;
    const response = await fetch(url, {
      method: state.profileId == null ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    const profile = await response.json();
    state.profileId = profile.id;
    state.optimization = profile.stream_mode;
    $("optimization").value = profile.stream_mode;
    await loadProfiles();
    $("profile").value = String(profile.id);
    $("status").textContent = `Saved playlist profile ${profile.name} · ${profile.stream_mode}`;
  } catch (error) {
    $("status").innerHTML = `<span class="error">Profile save failed: ${escapeHtml(error.message)}</span>`;
  }
}

$("profile").addEventListener("change", applySavedProfileMode);
$("save-profile").addEventListener("click", (event) => {
  event.stopImmediatePropagation();
  void saveProfileWithMode();
}, true);

const profileModeTimer = setInterval(() => {
  if (state.profileId != null && state.profiles.length) {
    applySavedProfileMode();
    clearInterval(profileModeTimer);
  }
}, 100);
