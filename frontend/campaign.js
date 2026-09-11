(() => {
  const TEST_RECOMMENDATIONS = [
    { id: "quick-daily", title: "Quick Daily", repeat: "Every 24 hours", testType: "quick", description: "Best for frequently changing playlists or services you rely on throughout the day." },
    { id: "quick-three-day", title: "Quick Every 3 Days", repeat: "Every 3 days", testType: "quick", description: "A balanced routine for keeping availability and startup performance fresh." },
    { id: "deep-weekly", title: "Deep Weekly", repeat: "Every 7 days", testType: "deep", description: "Validate real playback quality, stability, and sustained throughput." },
    { id: "deep-monthly", title: "Deep Monthly", repeat: "Every 30 days", testType: "deep", description: "A lower-frequency full baseline for stable playlists that rarely change." },
  ];

  function workerCount() {
    const value = Number($("test-concurrency").value || 4);
    return Number.isInteger(value) && value >= 1 && value <= 32 ? value : 4;
  }

  function setWorkerControlDisabled(disabled) {
    const control = $("test-concurrency");
    if (control) control.disabled = disabled;
  }

  function setCancelControl(visible, disabled = false) {
    const control = $("test-cancel");
    if (!control) return;
    control.hidden = !visible;
    control.disabled = disabled;
  }

  function renderTestRecommendations() {
    const panel = $("test-recommendations");
    const list = $("test-recommendation-list");
    const playlist = selectedPlaylist();
    if (!panel || !list) return;
    panel.hidden = !playlist || playlist.latest_version_id == null;
    if (panel.hidden) return;

    list.innerHTML = TEST_RECOMMENDATIONS.map((recommendation) => `
      <article class="test-recommendation">
        <div>
          <div class="test-recommendation-head">
            <strong>${recommendation.title}</strong>
            <span class="badge ${recommendation.testType === "deep" ? "" : "muted"}">${recommendation.testType === "deep" ? "Deep" : "Quick"}</span>
          </div>
          <div class="test-recommendation-repeat">Repeat ${recommendation.repeat}</div>
          <p class="meta">${recommendation.description}</p>
        </div>
        <button type="button" class="run-recommendation" data-test-type="${recommendation.testType}" ${state.polling ? "disabled" : ""}>Run now</button>
      </article>`).join("");
  }

  function renderCampaignStats(run) {
    const progress = $("test-progress");
    let stats = $("test-progress-stats");
    if (!stats) {
      stats = document.createElement("div");
      stats.id = "test-progress-stats";
      stats.className = "test-progress-stats";
      progress.querySelector(".progress-track")?.insertAdjacentElement("afterend", stats);
    }
    const total = run.total_streams || 0;
    const completed = run.completed_streams || 0;
    const success = run.successful_streams || 0;
    const failed = run.failed_streams || 0;
    const completion = total ? Math.round((completed / total) * 100) : 0;
    stats.innerHTML = [
      ["Completed", `${completed} / ${total}`],
      ["Successful", success],
      ["Failed", failed],
      ["Progress", `${completion}%`],
    ].map(([label, value]) => `<div class="metric"><div class="value">${value}</div><div class="label">${label}</div></div>`).join("");
  }

  function renderCampaignError(run) {
    const error = run.error || run.configuration?.error;
    const errorType = run.error_type || run.configuration?.error_type;
    const target = $("test-progress-error");
    if (!target) return;
    if (!error) {
      target.hidden = true;
      target.innerHTML = "";
      return;
    }
    target.hidden = false;
    target.innerHTML = `
      <div class="campaign-error-head"><strong>Campaign error</strong>${errorType ? `<span class="badge muted">${escapeHtml(errorType)}</span>` : ""}</div>
      <pre class="campaign-error-message">${escapeHtml(error)}</pre>`;
  }

  async function startCampaign(testType) {
    const playlist = selectedPlaylist();
    if (!playlist || playlist.latest_version_id == null || state.polling) return;

    state.testType = testType;
    const workers = workerCount();
    const label = testType === "deep" ? "Deep test campaign" : "Quick test campaign";
    $("status").textContent = `Starting ${label.toLowerCase()} for ${playlist.name} with ${workers} workers…`;
    setWorkerControlDisabled(true);
    setCancelControl(false);
    renderTestRecommendations();
    $("test-progress-error").hidden = true;

    try {
      const params = new URLSearchParams({ source_playlist_id: String(state.playlistId), test_type: testType, concurrency: String(workers) });
      const response = await fetch(`/api/stream-tests?${params.toString()}`, { method: "POST" });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `${response.status} ${response.statusText}`);
      }
      const run = await response.json();
      state.testRunId = run.test_run_id;
      setCancelControl(true);
      renderTestProgress(run);
      renderCampaignStats(run);
      renderCampaignError(run);
      await pollCampaign(run.test_run_id);
    } catch (error) {
      state.polling = false;
      setWorkerControlDisabled(false);
      setCancelControl(false);
      renderPlaylists();
      renderTestRecommendations();
      $("status").innerHTML = `<span class="error">Test campaign failed to start: ${escapeHtml(error.message)}</span>`;
    }
  }

  async function cancelCampaign() {
    const runId = state.testRunId;
    if (!runId || !state.polling) return;
    setCancelControl(true, true);
    $("status").textContent = "Stopping test campaign… active stream tests will finish, pending tests will be cancelled.";
    try {
      const response = await fetch(`/api/stream-tests/${runId}/cancel`, { method: "POST" });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `${response.status} ${response.statusText}`);
      }
    } catch (error) {
      setCancelControl(true, false);
      $("status").innerHTML = `<span class="error">Unable to cancel campaign: ${escapeHtml(error.message)}</span>`;
    }
  }

  async function pollCampaign(runId) {
    state.polling = true;
    renderPlaylists();
    renderTestRecommendations();
    try {
      while (true) {
        const run = await getJson(`/api/stream-tests/${runId}`);
        renderCampaignProgress(run);
        renderCampaignStats(run);
        renderCampaignError(run);
        if (["completed", "failed", "cancelled"].includes(run.status)) {
          state.polling = false;
          setWorkerControlDisabled(false);
          setCancelControl(false);
          renderPlaylists();
          renderTestRecommendations();
          await loadChannels();
          window.renderOverview?.();
          const label = state.testType === "deep" ? "Deep" : "Quick";
          if (run.status === "failed") {
            const detail = run.error || run.configuration?.error || "The campaign ended before stream results could be completed.";
            const type = run.error_type || run.configuration?.error_type;
            $("status").innerHTML = `<span class="error">${label} campaign failed: ${escapeHtml(type ? `${type}: ${detail}` : detail)}</span>`;
          } else {
            $("status").textContent = `${label} campaign ${run.status}: ${run.successful_streams} successful, ${run.failed_streams} failed`;
          }
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (error) {
      state.polling = false;
      setWorkerControlDisabled(false);
      setCancelControl(false);
      renderPlaylists();
      renderTestRecommendations();
      $("status").innerHTML = `<span class="error">Test campaign status error: ${escapeHtml(error.message)}</span>`;
    }
  }

  function renderCampaignProgress(run) {
    renderTestProgress(run);
    const workers = run.configuration?.concurrency;
    const typeLabel = state.testType === "deep" ? "Deep" : "Quick";
    if (run.status === "running" && workers) $("test-progress-label").textContent = `${typeLabel} campaign running · ${workers} workers`;
    if (run.configuration?.cancelled || run.status === "cancelled") $("test-progress-label").textContent = `${typeLabel} campaign cancellation complete`;
    if (run.status === "failed") $("test-progress-label").textContent = `${typeLabel} campaign failed`;
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.id === "test-cancel") {
      event.preventDefault();
      event.stopImmediatePropagation();
      cancelCampaign();
      return;
    }
    if (target.classList.contains("run-recommendation")) {
      event.preventDefault();
      event.stopImmediatePropagation();
      startCampaign(target.dataset.testType);
      return;
    }
    if (target.id === "test" || target.id === "deep-test") {
      event.preventDefault();
      event.stopImmediatePropagation();
      startCampaign(target.id === "deep-test" ? "deep" : "quick");
    }
  }, true);

  window.renderTestRecommendations = renderTestRecommendations;
})();
