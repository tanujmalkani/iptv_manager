function exportPreviewOptimization() {
  return state.optimization || "";
}

function exportPreviewParams() {
  const params = new URLSearchParams();
  const optimization = exportPreviewOptimization();
  if (optimization) params.set("optimization_profile", optimization);
  if (state.profileId != null) params.set("playlist_profile_id", state.profileId);
  return params.toString();
}

function exportPreviewFilename(preview) {
  const parts = ["iptv-manager"];
  if (preview.playlist_profile_id != null) parts.push(`profile-${preview.playlist_profile_id}`);
  parts.push(preview.optimization_profile || "original");
  return `${parts.join("-")}-v${preview.source_playlist_version_number}.m3u`;
}

function renderExportPreview(preview) {
  $("export-preview").hidden = false;
  $("export-preview-summary").textContent = `Source playlist v${preview.source_playlist_version_number} · ${preview.channel_count} channels will be exported`;
  $("export-preview-metrics").innerHTML = [
    ["Channels", preview.channel_count],
    ["Optimized", preview.optimized_count],
    ["Manual", preview.manual_selection_count],
    ["Automatic", preview.automatic_selection_count],
    ["Fallback", preview.fallback_count],
    ["Untested", preview.untested_count],
    ["No successful test", preview.no_successful_test_count],
    ["Duplicate entries", preview.duplicate_channel_entries],
  ].map(([label, value]) => `<div class="metric"><div class="value">${value}</div><div class="label">${escapeHtml(label)}</div></div>`).join("");

  const warnings = preview.warnings || [];
  $("export-preview-warnings").innerHTML = warnings.length
    ? `<strong>Review before export</strong><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
    : '<div class="export-ok"><strong>Ready to export.</strong> No validation warnings were found.</div>';
  $("export-confirm").disabled = preview.invalid_selection_count > 0;
}

async function showExportPreview() {
  if (state.playlistId == null || state.polling) return;
  const playlist = selectedPlaylist();
  if (!playlist || playlist.latest_version_id == null) return;

  $("status").textContent = "Validating export…";
  $("export-preview").hidden = false;
  $("export-preview-summary").textContent = "Loading export validation…";
  $("export-preview-metrics").innerHTML = "";
  $("export-preview-warnings").innerHTML = "";
  try {
    const query = exportPreviewParams();
    const preview = await getJson(`/api/source-playlists/${state.playlistId}/export-preview${query ? `?${query}` : ""}`);
    renderExportPreview(preview);
    $("status").textContent = preview.warnings.length
      ? "Export validation found items to review."
      : "Export validation passed.";
    $("export-preview").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    $("export-preview-summary").innerHTML = `<span class="error">Unable to validate export: ${escapeHtml(error.message)}</span>`;
    $("export-preview-metrics").innerHTML = "";
    $("export-preview-warnings").innerHTML = "";
    $("status").innerHTML = `<span class="error">Export validation failed: ${escapeHtml(error.message)}</span>`;
  }
}

async function confirmExport() {
  if (state.playlistId == null || state.polling) return;
  const playlist = selectedPlaylist();
  if (!playlist || playlist.latest_version_id == null) return;
  const query = exportPreviewParams();
  const response = await fetch(`/api/source-playlists/${state.playlistId}/export.m3u${query ? `?${query}` : ""}`);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : exportPreviewFilename({
    playlist_profile_id: state.profileId,
    optimization_profile: state.optimization,
    source_playlist_version_number: playlist.latest_version_number,
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  $("export-preview").hidden = true;
  $("status").textContent = `Exported ${filename}`;
}

$("export").addEventListener("click", (event) => {
  event.preventDefault();
  event.stopImmediatePropagation();
  showExportPreview();
}, true);
$("export-cancel").addEventListener("click", () => {
  $("export-preview").hidden = true;
  $("status").textContent = "Export cancelled.";
});
$("export-confirm").addEventListener("click", async () => {
  $("export-confirm").disabled = true;
  try {
    await confirmExport();
  } catch (error) {
    $("status").innerHTML = `<span class="error">Export failed: ${escapeHtml(error.message)}</span>`;
    $("export-confirm").disabled = false;
  }
});

$("optimization").addEventListener("change", () => {
  if (!$("export-preview").hidden) showExportPreview();
});
$("profile").addEventListener("change", () => {
  if (!$("export-preview").hidden) showExportPreview();
});
