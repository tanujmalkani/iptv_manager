(() => {
  async function selectImportedPlaylist(result) {
    state.playlistId = result.source_playlist_id;
    state.selectedId = null;
    state.profileId = null;
    await loadPlaylists();
    state.playlistId = result.source_playlist_id;
    renderPlaylists();
    await loadChannels();
    await loadProfiles();
    window.renderOverview?.();
    window.showPage?.("channels");
    $("status").textContent = `Selected imported playlist · v${result.version_number}`;
  }

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
      try {
        await selectImportedPlaylist(result);
      } catch (error) {
        $("status").innerHTML = `<span class="error">Unable to load imported playlist: ${escapeHtml(error.message)}</span>`;
      }
    });
  }

  function ensureFilePicker() {
    if ($("import-file") || !$("import-content")) return;
    const contentLabel = $("import-content").closest("label");
    if (!contentLabel) return;

    const picker = document.createElement("div");
    picker.className = "import-source-picker";

    const description = document.createElement("div");
    description.innerHTML = '<span>Import from file</span><p class="meta">Load an M3U playlist from your computer into the editor.</p>';

    const actions = document.createElement("div");
    actions.className = "import-file-actions";

    const fileName = document.createElement("span");
    fileName.id = "import-file-name";
    fileName.className = "meta";
    fileName.textContent = "No file selected";

    const fileInput = document.createElement("input");
    fileInput.id = "import-file";
    fileInput.type = "file";
    fileInput.accept = ".m3u,.m3u8,.txt,text/plain,application/vnd.apple.mpegurl,audio/mpegurl";
    fileInput.className = "sr-only";

    const button = document.createElement("button");
    button.id = "import-file-button";
    button.type = "button";
    button.className = "secondary-button";
    button.textContent = "Upload M3U file";
    button.addEventListener("click", () => fileInput.click());

    actions.append(button, fileName, fileInput);
    picker.append(description, actions);
    contentLabel.parentNode.insertBefore(picker, contentLabel);
  }

  function bindFilePicker() {
    const button = $("import-file-button");
    const input = $("import-file");
    if (!button || !input) return;
    button.addEventListener("click", () => {
      input.click();
    });
  }

  ensureFilePicker();
  bindFilePicker();

  $("import-file")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const supported = /\.(m3u8?|txt)$/i.test(file.name);
    if (!supported) {
      $("import-file-name").textContent = "Unsupported file type";
      $("status").textContent = "Please choose an .m3u, .m3u8, or .txt playlist file.";
      event.target.value = "";
      return;
    }

    try {
      const text = await file.text();
      if (!text.trim()) throw new Error("The selected file is empty.");
      $("import-content").value = text;
      $("import-file-name").textContent = file.name;
      if (!$("import-name").value.trim()) {
        $("import-name").value = file.name.replace(/\.(m3u8?|txt)$/i, "");
      }
      $("status").textContent = `Loaded ${file.name} into the playlist editor.`;
    } catch (error) {
      $("import-file-name").textContent = "Unable to read file";
      $("status").textContent = `File load failed: ${escapeHtml(error.message)}`;
      event.target.value = "";
    }
  });

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
      $("import-form").reset();
      $("import-file").value = "";
      $("import-file-name").textContent = "No file selected";
      await selectImportedPlaylist(importResult);
    } catch (error) {
      result.hidden = false;
      result.innerHTML = `<span class="error">Import failed: ${escapeHtml(error.message)}</span>`;
      $("status").innerHTML = `<span class="error">Import failed: ${escapeHtml(error.message)}</span>`;
    } finally {
      submit.disabled = false;
    }
  });
})();
