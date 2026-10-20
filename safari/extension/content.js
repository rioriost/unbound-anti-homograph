(() => {
    "use strict";
    if (window.top !== window) return;

    const result = AntiHomograph.analyzeURL(location.href);
    if (result.status !== "warning") return;

    const { message, element, render } = AntiHomographUI;
    const host = document.createElement("aside");
    // Isolate site styling, not trust: a hostile page can still remove this host.
    host.style.cssText = "all:initial!important;display:block!important;position:fixed!important;" +
        "inset:0 0 auto 0!important;z-index:2147483647!important;" +
        "max-height:70vh!important;overflow:auto!important;color-scheme:light dark!important;";
    const root = host.attachShadow({ mode: "closed" });
    const style = element("style");
    style.textContent = `
        :host { color-scheme: light dark; }
        section { box-sizing: border-box; background: #fff8eb; color: #25221d;
            border: 3px solid #956000; padding: 20px; font: 16px/1.5 system-ui, sans-serif;
            text-align: start; overflow-wrap: anywhere; }
        h1 { font-size: 1.15em; margin: 0 0 8px; }
        p, dl, ul { margin: 8px 0; }
        dt { font-weight: 600; } dd { margin: 0 0 4px; font-family: ui-monospace, monospace; }
        ul { padding-inline-start: 24px; }
        .note { font-size: .875em; }
        nav { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
        button { font: inherit; padding: 8px 16px; min-height: 44px; border-radius: 6px;
            border: 1px solid #625e56; background: #fff; color: #25221d; cursor: pointer; }
        button.primary { background: #25221d; color: #fff; }
        button:focus-visible { outline: 3px solid #0067c0; outline-offset: 3px; }
        @media (prefers-color-scheme: dark) {
            section { background: #29251d; color: #fff5e3; border-color: #edbd62; }
            button { background: #29251d; color: #fff5e3; border-color: #edbd62; }
            button.primary { background: #fff5e3; color: #29251d; }
            button:focus-visible { outline-color: #8bc9ff; }
        }
        @media (forced-colors: active) {
            section, button, button.primary { background: Canvas; color: CanvasText; border-color: CanvasText; }
        }
    `;
    const section = element("section");
    section.lang = browser.i18n.getUILanguage();
    section.setAttribute("aria-label", message("extensionName"));
    const title = render(section, result);
    // Announce the warning without moving keyboard focus away from the page.
    title.setAttribute("role", "alert");
    const actions = element("nav");
    actions.setAttribute("aria-label", message("extensionName"));
    const dismiss = element("button", message("dismissButton"));
    const leave = element("button", message("leaveButton"), "primary");
    dismiss.type = leave.type = "button";
    dismiss.addEventListener("click", () => host.remove());
    leave.addEventListener("click", () => location.replace("about:blank"));
    actions.append(dismiss, leave);
    section.append(actions);
    root.append(style, section);

    function mount() {
        if (!document.documentElement) return false;
        document.documentElement.append(host);
        return true;
    }
    if (!mount()) {
        const observer = new MutationObserver(() => {
            if (mount()) observer.disconnect();
        });
        observer.observe(document, { childList: true });
    }
})();
