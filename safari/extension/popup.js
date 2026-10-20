/* global AntiHomograph, AntiHomographUI, browser */
(async () => {
    "use strict";
    const container = document.getElementById("result");
    const { message, render } = AntiHomographUI;
    document.documentElement.lang = browser.i18n.getUILanguage();
    container.textContent = message("loading");
    let result;
    try {
        const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
        result = tab?.url ? AntiHomograph.analyzeURL(tab.url) : { status: "error" };
    } catch (error) {
        console.error("Anti-Homograph: unable to inspect the active tab", error);
        result = { status: "error" };
    }
    container.replaceChildren();
    container.dataset.status = result.status;
    render(container, result);
    container.setAttribute("aria-busy", "false");
})();
