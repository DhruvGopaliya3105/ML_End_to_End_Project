
// ---- safety net 1: any JS error becomes a visible banner ----
// (this tiny block runs even if the main script below has a syntax error)
window.addEventListener("error", function (e) {
  try {
    var banner = document.createElement("div");
    banner.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:9999;background:#b91c1c;color:#fff;padding:10px 16px;font:13px sans-serif";
    banner.textContent = "Page script error: " + (e.message || e.type) +
      " - hard-refresh (Ctrl+F5), or re-paste templates/newpage.html (complete file, ends with the closing html tag).";
    document.body.appendChild(banner);
  } catch (_) {}
});
