(() => {
  const validPages = new Set(["overview", "import", "channels", "testing", "export"]);
  const storageKey = "iptv-manager-page";

  function showPage(page, updateHash = true) {
    const nextPage = validPages.has(page) ? page : "overview";
    document.querySelectorAll(".page").forEach((section) => {
      const active = section.dataset.page === nextPage;
      section.hidden = !active;
      section.classList.toggle("active", active);
    });
    document.querySelectorAll(".nav-tab").forEach((button) => {
      const active = button.dataset.page === nextPage;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    try { localStorage.setItem(storageKey, nextPage); } catch (_) { /* Ignore unavailable storage. */ }
    if (updateHash && window.location.hash !== `#${nextPage}`) {
      history.replaceState(null, "", `#${nextPage}`);
    }
    window.dispatchEvent(new CustomEvent("iptv:pagechange", { detail: { page: nextPage } }));
  }

  function initialPage() {
    const hash = window.location.hash.slice(1);
    if (validPages.has(hash)) return hash;
    try {
      const saved = localStorage.getItem(storageKey);
      if (validPages.has(saved)) return saved;
    } catch (_) { /* Ignore unavailable storage. */ }
    return "overview";
  }

  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.page));
  });

  window.addEventListener("hashchange", () => showPage(window.location.hash.slice(1), false));
  window.showPage = showPage;
  showPage(initialPage(), false);
})();
