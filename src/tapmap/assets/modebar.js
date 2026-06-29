/* Plotly modebar custom buttons and actions. */

// Dash creates the Plotly modebar after page load.
// Wait until it exists before inserting the custom button.
const observer = new MutationObserver(() => {
    const groups = document.querySelectorAll(".modebar-group");

    if (groups.length < 3) {
        return;
    }

    // Already added.
    if (document.querySelector('[aria-label="Fit Connections"]')) {
        observer.disconnect();
        return;
    }

    const fitButton = groups[2].lastElementChild.cloneNode(true);

    fitButton.setAttribute("data-title", "Fit Connections");
    fitButton.setAttribute("aria-label", "Fit Connections");

    // Replace the Reset icon.
    fitButton.querySelector("svg").outerHTML = `
<svg class="icon" viewBox="0 0 24 24" height="1em" width="1em">
  <path
    d="M3 9V3h6v2H5v4H3zm16 0V5h-4V3h6v6h-2zM3 15h2v4h4v2H3v-6zm16 4v-4h2v6h-6v-2h4z"
    style="fill: rgba(255,255,255,0.3);">
  </path>
</svg>`;

    fitButton.addEventListener("click", () => {
        window.sendToken("__z__");
    });

    // Insert before Zoom In.
    groups[2].insertBefore(fitButton, groups[2].firstChild);

    observer.disconnect();
});

observer.observe(document.body, {
    childList: true,
    subtree: true,
});
