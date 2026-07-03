/* Shutdown confirmation handshake. */
/*
 * Waits until the shutdown modal has been rendered in the browser,
 * then signals Python to perform the actual shutdown.
 *
 * Using a MutationObserver avoids a race condition where the server
 * terminates before the browser has received and rendered the modal.
 * The signal is sent as soon as the shutdown screen enters the DOM —
 * no arbitrary delays are needed.
 */

(function () {
    const observer = new MutationObserver(function () {
        if (document.getElementById("shutdown_screen")) {
            observer.disconnect();
            window.sendToken("__exit_confirmed__");
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
    });
})();
