
// ---- safety net 2: if the main script failed, replace endless Loading… ----
setTimeout(function () {
  document.querySelectorAll(".mcp-loading").forEach(function (el) {
    el.innerHTML = '<div class="mcp-error">Data script did not run - hard refresh (Ctrl+F5), or re-paste templates/newpage.html (complete file, ends with the closing html tag).</div>';
  });
}, 5000);
