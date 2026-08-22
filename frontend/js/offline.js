/**
 * Fruvia AI — Offline Page Script
 */

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("btn-retry-offline");
  if (btn) {
    btn.addEventListener("click", () => window.location.reload());
  }
});
