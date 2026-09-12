(() => {
  function setStatus(message, busy = false, error = false) {
    const status = $("status");
    if (!status) return;
    status.dataset.busy = busy ? "true" : "false";
    status.classList.toggle("status-error", error);
    if (error) status.innerHTML = `<span class="error">${escapeHtml(message)}</span>`;
    else status.textContent = message;
  }

  function setImportControlsDisabled(disabled) {
    ["import-name", "import-source-location", "import-content", "import-file-button"].forEach((id) => {
      const control = $(id);
      if (control) control.disabled = disabled;
    });
  }

  function renderImportProgress(job) {
    const progress = $("import-progress");
    if (!progress) return;
    progress.hidden = false;

    const total = job.total || 0;
    const current = job.current || 0;
    const percent = total ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const labels = {
      queued: "Queued",
      starting: "Starting",
      parsing: "Parsing",
      parsed: "Parsed",
      discovering: "Discovering streams",
      saving: "Saving",
      complete: "Complete",
      failed: "Failed",
    };

    $("import-progress-label").textContent = job.status === "completed"
      ? "Playlist import complete"
      : job.status === "failed" ? "Playlist import failed" : "Importing playlist";
    $("import-progress-count").textContent = total ? `${current} / ${total}` : "";
    $("import-progress-stage").textContent = labels[job.stage] || job.stage || "Working";
    $("import-progress-stage").className = `badge ${job.status === "failed" ? "error-badge" : job.status === "completed" ? "" : "muted"}`;
    $("import-progress-bar").style.width = `${percent}%`;
    $("import-progress-message").textContent = job.message || "Working…";

    const error = $("import-progress-error");
    if (job.error) {
      error.hidden = false;
      error.innerHTML = `<div class="campaign-error-head"><strong>Import error</strong>${job.error_type ? `<span class="badge muted">${escapeHtml(job.error_type)}</span>` : ""}</div><pre class="campaign-error-message">${escapeHtml(job.error)}</pre>`;
    } else {
      error.hidden = true;
      error.innerHTML = "";
    }
  }

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
    setStatus(`Selected imported playlist · v${result.version_number}`);
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
        setStatus(`Unable to load imported playlist: ${error.message}`, false, true);
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

  async function pollImport(importId) {
    state.polling = true;
    setImportControlsDisabled(true);
    try {
      while (true) {
        const job = await getJson(`/api/source-playlists/import/${encodeURIComponent(importId)}`);
        renderImportProgress(job);
        const playlistName = $("import-name").value.trim() || "playlist";
        if (job.status === "running" || job.status === "pending") {
          setStatus(job.message || `Importing ${playlistName}…`, true);
        }
        if (["completed", "failed"].includes(job.status)) {
          state.polling = false;
          setImportControlsDisabled(false);
          if (job.status === "failed") {
            const detail = job.error || "The playlist import ended unexpectedly.";
            setStatus(`Import failed: ${job.error_type ? `${job.error_type}: ${detail}` : detail}`, false, true);
            return;
          }
          const result = job.result;
          if (!result) throw new Error("Import completed without a result.");
          renderImportResult(result);
          $("import-form").reset();
          $("import-file").value = "";
          $("import-file-name").textContent = "No file selected";
          setStatus("Import complete · refreshing playlist data…", true);
          await selectImportedPlaylist(result);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 750));
      }
    } catch (error) {
      state.polling = false;
      setImportControlsDisabled(false);
      setStatus(`Import status error: ${error.message}`, false, true);
    }
  }

  ensureFilePicker();
  bindFilePicker();

  $("import-file")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const supported = /\.(m3u8?|txt)$/i.test(file.name);
    if (!supported) {
      $("import-file-name").textContent = "Unsupported file type";
      setStatus("Please choose an .m3u, .m3u8, or .txt playlist file.");
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
      setStatus(`Loaded ${file.name} into the playlist editor.`);
    } catch (error) {
      $("import-file-name").textContent = "Unable to read file";
      setStatus(`File load failed: ${error.message}`, false, true);
      event.target.value = "";
    }
  });

  $("import-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("import-submit");
    const result = $("import-result");
    const progress = $("import-progress");
    const name = $("import-name").value.trim();
    const text = $("import-content").value;
    const sourceLocation = $("import-source-location").value.trim();
    if (!name || !text.trim() || state.polling) return;

    submit.disabled = true;
    result.hidden = true;
    progress.hidden = false;
    renderImportProgress({ status: "pending", stage: "queued", current: 0, total: 0, message: "Waiting to start" });
    setStatus(`Starting import for ${name}…`, true);
    setImportControlsDisabled(true);
    try {
      const response = await fetch("/api/source-playlists/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, text, source_location: sourceLocation || null }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `${response.status} ${response.statusText}`);
      }
      const importJob = await response.json();
      await pollImport(importJob.import_id);
    } catch (error) {
      state.polling = false;
      setImportControlsDisabled(false);
      result.hidden = false;
      result.innerHTML = `<span class="error">Import failed to start: ${escapeHtml(error.message)}</span>`;
      setStatus(`Import failed to start: ${error.message}`, false, true);
    } finally {
      submit.disabled = false;
    }
  });
})();
