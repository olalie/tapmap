(function () {
  function isTypingTarget(el) {
    if (!el) return false;

    // Do not block shortcuts when target is the technical capture field
    if ((el.id || "") === "key_capture") return false;

    const tag = (el.tagName || "").toLowerCase();
    if (tag !== "input" && tag !== "textarea" && !el.isContentEditable) return false;

    // Only treat text-like inputs as typing targets.
    // Checkboxes/radios should not block ESC and shortcuts.
    if (tag === "input") {
      const t = (el.type || "").toLowerCase();
      const typingTypes = new Set([
        "", "text", "search", "email", "url", "tel", "password",
        "number", "date", "datetime-local", "month", "time", "week",
      ]);
      return typingTypes.has(t);
    }

    return true; // textarea or contentEditable
  }


  function setNativeValue(el, value) {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    ).set;
    setter.call(el, value);
  }

  function sendToken(token) {
    const inp = document.getElementById("key_capture");
    if (!inp) return;

    const v = token + "|" + Date.now();
    setNativeValue(inp, v);

    // Må være input-event for at Dash skal trigge callbacken
    inp.dispatchEvent(new Event("input", { bubbles: true }));
  }

  window.addEventListener(
    "keydown",
    function (e) {
      if (isTypingTarget(e.target)) return;

      const k = (e.key || "").toLowerCase();

      if (e.key === "Escape") {
        e.preventDefault();
        sendToken("__esc__");
        return;
      }

      if (k === "i" || k === "u" || k === "o" || k === "l" || k === "g" || k === "t" || k === "c" || k === "h" || k === "a" || k === "d") {
        sendToken("__" + k + "__");
      }
    },
    true
  );

  // Enforce mutual exclusion: only one accordion section open at a time.
  // Scoped to #menu_panel — ignores <details> elements elsewhere in the page.
  document.addEventListener(
    "toggle",
    function (e) {
      if (!e.target || e.target.tagName !== "DETAILS") return;
      if (!e.target.open) return;
      var panel = document.getElementById("menu_panel");
      if (!panel || !panel.contains(e.target)) return;
      panel.querySelectorAll("details.mx-acc-section").forEach(function (d) {
        if (d !== e.target) d.open = false;
      });
    },
    true
  );
})();


/* GeoDB meldinger */

document.addEventListener("click", (event) => {
    if (event.target.id === "btn_install_dbip") {
        const status = document.getElementById("geodb-status-dbip");

        if (status) {
            status.innerHTML = `
                <span class="mx-status__value geodb-running">
                    Installing DB-IP databases...
                </span>
            `;
        }
    }

    if (event.target.id === "btn_install_maxmind") {
        const status = document.getElementById("geodb-status-maxmind");

        if (status) {
            status.innerHTML = `
                <span class="mx-status__value geodb-running">
                    Installing MaxMind databases...
                </span>
            `;
        }
    }

    if (event.target.id === "btn_update_databases") {
        const working = document.getElementById("geodb-working");

        if (working) {
            working.textContent = "Checking for updates...";
            working.classList.add("geodb-running");
        }
    }
});


