/* Single-open accordion for the menu panel. */

document.addEventListener(
    "toggle",
    (event) => {
        if (!event.target || event.target.tagName !== "DETAILS") {
            return;
        }

        if (!event.target.open) {
            return;
        }

        const panel = document.getElementById("menu_panel");

        if (!panel || !panel.contains(event.target)) {
            return;
        }

        panel.querySelectorAll("details.mx-acc-section").forEach((details) => {
            if (details !== event.target) {
                details.open = false;
            }
        });
    },
    true,
);
