(() => {
  function renderImportResult(result) {
    const target = $("import-result");
    target.hidden = false;
    const title = result.identical_version ? "Existing version detected" : `Imported version v${result.version_number}`;
    target.innerHTML = `
      <div class="import-result-head">
        <div><strong>${title}</strong><p class="meta">${result.entries} source entries · ${result.channels} channels · ${result.unique_streams} unique streams</p></div>
        <button type="button" id="open-imported-playlist">Use this playlist</button>
      </div>
      <div class="import-result-metrics">
        <span>${result.discovered_streams} discovered</span>
        <span>${result.duplicate_urls} duplicate URLs</span>
        <span>${result.new_channels} new channels</span>
      </div>
      ${result.warnings?.length ? `<div class="import-warnings"><strong>Warnings</strong><ul>${result.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>` : ""}`;
    $("open-imported-playlist").addEventListener("click", async () => {
      await loadPlaylists();
      state.playlistId = result.source_playlist_id;
      state.selectedId = null;
      await loadChannels();
      await loadProfiles();
      renderPlaylists();
      window.renderOverview?.();
      window.showPage?.("channels");
      $("status").textContent = `Selected imported playlist · v${result.version_number}`;
    });
  }

  $("import-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("import-submit");
    const result = $("import-result");
    const name = $("import-name").value.trim();
    const text = $("import-content").value;
    const sourceLocation = $("import-source-location").value.trim();
    if (!name || !text.trim()) return;

    submit.disabled = true;
    result.hidden = true;
    $("status").textContent = "Importing playlist and discovering streams…";
    try {
      const response = await fetch("/api/source-playlists/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, text, source_location: sourceLocation || null }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `${response.status} ${response.statusText}`);
      }
      const importResult = await response.json();
      renderImportResult(importResult);
      $("status").textContent = importResult.identical_version
        ? "Import matched an existing playlist version."
        : `Playlist imported successfully as version ${importResult.version_number}.`;
      $("import-form").reset();
      window.dispatchEvent(new CustomEvent("iptv:datachange"));
    } catch (error) {
      result.hidden = false;
      result.innerHTML = `<span class="error">Import failed: ${escapeHtml(error.message)}</span>`;
      $("status").innerHTML = `<span class="error">Import failed: ${escapeHtml(error.message)}</span>`;
    } finally {
      submit.disabled = false;
    }
  });
})();
