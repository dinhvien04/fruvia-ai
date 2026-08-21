/**
 * Fruvia AI — Responsive Navigation & Mobile Bottom Nav Module
 */
const Navigation = {
  init() {
    this.highlightActiveLinks();
  },

  highlightActiveLinks() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll(".nav-link, .mobile-nav-item");

    navLinks.forEach((link) => {
      const href = link.getAttribute("href");
      if (!href) return;

      if (
        (href === "/" && (currentPath === "/" || currentPath === "/index.html")) ||
        (href === "/search" && (currentPath === "/search" || currentPath === "/retrieval.html")) ||
        (href === "/explore" && (currentPath === "/explore" || currentPath === "/explore.html"))
      ) {
        link.classList.add("active");
        link.setAttribute("aria-current", "page");
      } else {
        link.classList.remove("active");
        link.removeAttribute("aria-current");
      }
    });
  }
};

document.addEventListener("DOMContentLoaded", () => Navigation.init());
