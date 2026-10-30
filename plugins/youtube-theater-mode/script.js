// YouTube theater mode. Runs on matching pages; turns theater mode on for every watch page.
if (window.__valerieTheater) return;
window.__valerieTheater = true;
let timer = 0;

// The player is built after the page loads, so retry until its theater button exists.
function enable(attempt = 0) {
  if (location.pathname !== "/watch") return;
  const button = document.querySelector(".ytp-size-button");
  if (!button) {
    if (attempt < 40) setTimeout(() => enable(attempt + 1), 500);
    return;
  }
  const label = button.getAttribute("title") || button.getAttribute("aria-label") || "";
  if (label.startsWith("Theater mode")) button.click();
}

// YouTube changes pages without reloading; it announces each one with this event.
function schedule() {
  clearTimeout(timer);
  timer = setTimeout(() => enable(0), 300);
}

document.addEventListener("yt-navigate-finish", schedule);
schedule();
