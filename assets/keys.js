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

      if (k === "o" || k === "u" || k === "t" || k === "c" || k === "r" || k === "h" || k === "a") {
        sendToken("__" + k + "__");
      }
    },
    true
  );
})();
