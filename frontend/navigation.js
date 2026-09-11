(() => {
  const validPages = new Set(["overview", "import", "channels", "testing", "export"]);
  const pageStorageKey = "iptv-manager-page";
  const themeStorageKey = "iptv-manager-theme";

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
    try { localStorage.setItem(pageStorageKey, nextPage); } catch (_) { /* Ignore unavailable storage. */ }
    if (updateHash && window.location.hash !== `#${nextPage}`) {
      history.replaceState(null, "", `#${nextPage}`);
    }
    window.dispatchEvent(new CustomEvent("iptv:pagechange", { detail: { page: nextPage } }));
  }

  function initialPage() {
    const hash = window.location.hash.slice(1);
    if (validPages.has(hash)) return hash;
    try {
      const saved = localStorage.getItem(pageStorageKey);
      if (validPages.has(saved)) return saved;
    } catch (_) { /* Ignore unavailable storage. */ }
    return "overview";
  }

  function applyTheme(theme) {
    const nextTheme = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = nextTheme;
    const toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.textContent = nextTheme === "dark" ? "☀" : "☾";
      toggle.title = nextTheme === "dark" ? "Switch to light mode" : "Switch to dark mode";
      toggle.setAttribute("aria-label", toggle.title);
    }
    try { localStorage.setItem(themeStorageKey, nextTheme); } catch (_) { /* Ignore unavailable storage. */ }
    window.dispatchEvent(new CustomEvent("iptv:themechange", { detail: { theme: nextTheme } }));
  }

  function initialTheme() {
    try {
      const saved = localStorage.getItem(themeStorageKey);
      if (saved === "dark" || saved === "light") return saved;
    } catch (_) { /* Ignore unavailable storage. */ }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.page));
  });
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
  window.addEventListener("hashchange", () => showPage(window.location.hash.slice(1), false));
  window.showPage = showPage;

  applyTheme(initialTheme());
  showPage(initialPage(), false);
})();
