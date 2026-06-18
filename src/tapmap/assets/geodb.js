/* GeoDB operation status messages. */
document.addEventListener("click", (event) => {
    const messages = {
        btn_install_dbip: "Installing DB-IP databases...",
        btn_install_maxmind: "Installing MaxMind databases...",
        btn_update_databases: "Checking for updates...",
        btn_check_databases: "Rechecking databases...",
    };

    const text = messages[event.target.id];

    if (!text) {
        return;
    }

    const status = document.getElementById("geodb-status-text");

    if (!status) {
        return;
    }

    status.textContent = text;
    status.classList.add("geodb-running");
});
