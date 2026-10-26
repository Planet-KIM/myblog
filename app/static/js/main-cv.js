/**
 * @file About / CV page (templates/main.html) toolbar and section switches.
 *
 * - KO/EN switch (#btn-lang-ko / #btn-lang-en) shows #cv-lang-ko or
 *   #cv-lang-en and remembers the choice in localStorage "cv-lang".
 * - Theme button (#btn-theme) flips the page theme, keeps the navbar theme
 *   icon in sync and saves it to localStorage "theme" / "cv-theme".
 * - Print button ([data-cv-print]) opens the browser's print dialog
 *   (save as PDF).
 * - Skills/Research switch (#btn-skills-mode / #btn-research-mode) swaps
 *   #skills-view and #research-view and the section title.
 *
 * Loaded without defer right after the CV markup: the saved language and
 * theme are applied as soon as the script runs, the Skills/Research switch is
 * wired on DOMContentLoaded.
 */

/**
 * Apply the saved language and theme, then wire the KO/EN switch, the theme
 * button and the print button.
 *
 * @returns {void}
 */
(function initCvToolbar() {
  const koBtn = document.getElementById("btn-lang-ko");
  const enBtn = document.getElementById("btn-lang-en");
  const koCv = document.getElementById("cv-lang-ko");
  const enCv = document.getElementById("cv-lang-en");
  const themeBtn = document.getElementById("btn-theme");
  const root = document.documentElement;

  /**
   * Show one CV language version, mark its button active and remember it.
   *
   * @param {'ko'|'en'} lang - Language to show.
   * @returns {void}
   */
  function setLang(lang) {
    if (!koBtn || !enBtn || !koCv || !enCv) return;
    const isKo = lang === "ko";

    koCv.classList.toggle("d-none", !isKo);
    enCv.classList.toggle("d-none", isKo);

    koBtn.classList.toggle("active", isKo);
    enBtn.classList.toggle("active", !isKo);

    try {
      localStorage.setItem("cv-lang", lang);
    } catch (e) {}
  }

  /**
   * Show the sun/moon icon on the navbar theme toggle for a theme.
   *
   * @param {'light'|'dark'} theme - The theme now applied.
   * @returns {void}
   */
  function syncGlobalThemeIcon(theme) {
    const navThemeToggle = document.querySelector(".theme-toggle");
    if (!navThemeToggle) return;
    navThemeToggle.innerHTML =
      theme === "dark"
        ? '<i class="bi bi-sun"></i>'
        : '<i class="bi bi-moon"></i>';
  }

  /**
   * Apply a theme to the page, update the theme button and navbar icon,
   * and save it.
   *
   * @param {string} theme - "dark" for dark; anything else means light.
   * @returns {void}
   */
  function setTheme(theme) {
    const normalized = theme === "dark" ? "dark" : "light";
    const isDark = normalized === "dark";
    root.setAttribute("data-theme", normalized);
    document.body.setAttribute("data-bs-theme", normalized);
    if (themeBtn) {
      themeBtn.textContent = isDark ? "라이트 모드" : "다크 모드";
      themeBtn.setAttribute("aria-label", `Switch to ${isDark ? "light" : "dark"} mode`);
    }
    syncGlobalThemeIcon(normalized);
    try {
      localStorage.setItem("theme", normalized);
      localStorage.setItem("cv-theme", normalized);
    } catch (e) {}
  }

  let savedLang = null;
  let savedTheme = null;
  try {
    savedLang = localStorage.getItem("cv-lang");
    savedTheme =
      localStorage.getItem("theme") ||
      localStorage.getItem("cv-theme") ||
      document.body.getAttribute("data-bs-theme") ||
      root.getAttribute("data-bs-theme") ||
      root.getAttribute("data-theme");
  } catch (e) {}

  setLang(savedLang === "en" ? "en" : "ko");
  setTheme(savedTheme === "dark" ? "dark" : "light");

  if (koBtn) {
    koBtn.addEventListener("click", function (e) {
      e.preventDefault();
      setLang("ko");
    });
  }
  if (enBtn) {
    enBtn.addEventListener("click", function (e) {
      e.preventDefault();
      setLang("en");
    });
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function (e) {
      e.preventDefault();
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      setTheme(next);
    });
  }

  document.querySelectorAll("[data-cv-print]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      window.print();
    });
  });
})();

/**
 * Wire the Skills/Research switch once the DOM is ready.
 *
 * @returns {void}
 */
document.addEventListener("DOMContentLoaded", function initSkillSwitch() {
  const btnSkills = document.getElementById("btn-skills-mode");
  const btnResearch = document.getElementById("btn-research-mode");
  const skillView = document.getElementById("skills-view");
  const researchView = document.getElementById("research-view");
  const titleSpan = document.getElementById("skill-section-title-text");

  /**
   * Switch the skills section between the Skills and Research views and
   * update the switch buttons and the section title.
   *
   * @param {'skills'|'research'} mode - View to show.
   * @returns {void}
   */
  function setSkillMode(mode) {
    if (!skillView || !researchView) return;
    const isSkills = mode === "skills";

    skillView.classList.toggle("d-none", !isSkills);
    researchView.classList.toggle("d-none", isSkills);

    if (btnSkills) btnSkills.classList.toggle("active", isSkills);
    if (btnResearch) btnResearch.classList.toggle("active", !isSkills);

    if (titleSpan) {
      titleSpan.textContent = isSkills ? "기술 스택" : "연구 관심사";
    }
  }

  if (btnSkills) {
    btnSkills.addEventListener("click", () => setSkillMode("skills"));
  }
  if (btnResearch) {
    btnResearch.addEventListener("click", () => setSkillMode("research"));
  }
});
