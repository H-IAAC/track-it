/* H.IAAC Toolkit — light/dark theme switch shared by every web tool.
   Any element with [data-hx-theme-toggle] toggles the theme (works for
   elements rendered later, e.g. by Dash). */
(function () {
  var KEY = "hiaac-theme";
  function apply(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem(KEY, t); } catch (e) {}
    document.dispatchEvent(new CustomEvent("hiaac-theme", { detail: t }));
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (!document.documentElement.dataset.theme || saved) apply(saved || "light");
  window.hiaacTheme = {
    get: function () { return document.documentElement.dataset.theme || "light"; },
    set: apply,
    toggle: function () { apply(this.get() === "dark" ? "light" : "dark"); }
  };
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-hx-theme-toggle]")) window.hiaacTheme.toggle();
  });
})();
