(() => {
  function workerCount() {
    const value = Number($("test-concurrency").value || 4);
    return Number.isInteger(value) && value >= 1 && value <= 32 ? value : 4;
  }

  function setWorkerControlDisabled(disabled) {
    const control = $("test-concurrency");
    if (control) control.disabled = disabled;
  }

  async function startCampaign(testType) {
    const playlist = selectedPlaylist();
    if (!playlist || playlist.latest_version_id == null || state.polling) return;

    state.testType = testType;
    const workers = workerCount();
    const label = testType === "deep" ? "Deep test campaign" : "Quick test campaign";
    $("status").textContent = `Starting ${label.toLowerCase()} for ${playlist.name} with ${workers} workers…`;
    setWorkerControlDisabled(true);

    try {
      const params = new URLSearchParams({
        source_playlist_id: String(state.playlistId),
        test_type: testType,
        concurrency: String(workers),
      });
      const response = await fetch(`/api/stream-tests?${params.toString()}`, { method: "POST" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const run = await response.json();
      state.testRunId = run.test_run_id;
      renderTestProgress(run);
      await pollCampaign(run.test_run_id);
    } catch (error) {
      state.polling = false;
      setWorkerControlDisabled(false);
      renderPlaylists();
      $("status").innerHTML = `<span class="error">Test campaign failed to start: ${escapeHtml(error.message)}</span>`;
    }
  }

  async function pollCampaign(runId) {
    state.polling = true;
    renderPlaylists();
    try {
      while (true) {
        const run = await getJson(`/api/stream-tests/${runId}`);
        renderCampaignProgress(run);
        if (["completed", "failed", "cancelled"].includes(run.status)) {
          state.polling = false;
          setWorkerControlDisabled(false);
          renderPlaylists();
          await loadChannels();
          const label = state.testType === "deep" ? "Deep" : "Quick";
          $("status").textContent = `${label} campaign ${run.status}: ${run.successful_streams} successful, ${run.failed_streams} failed`;
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (error) {
      state.polling = false;
      setWorkerControlDisabled(false);
      renderPlaylists();
      $("status").innerHTML = `<span class="error">Test campaign status error: ${escapeHtml(error.message)}</span>`;
    }
  }

  function renderCampaignProgress(run) {
    renderTestProgress(run);
    const workers = run.configuration?.concurrency;
    const typeLabel = state.testType === "deep" ? "Deep" : "Quick";
    if (run.status === "running" && workers) {
      $("test-progress-label").textContent = `${typeLabel} campaign running · ${workers} workers`;
    }
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.id === "test" || target.id === "deep-test") {
      event.preventDefault();
      event.stopImmediatePropagation();
      startCampaign(target.id === "deep-test" ? "deep" : "quick");
    }
  }, true);
})();
