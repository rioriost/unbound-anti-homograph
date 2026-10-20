(() => {
    "use strict";

    const message = key => browser.i18n.getMessage(key);

    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text) node.textContent = text;
        if (className) node.className = className;
        return node;
    }

    function render(container, result) {
        const status = result.status;
        const titleKey = status === "warning" ? "warningTitle"
            : status === "clear" ? "clearTitle"
            : status === "unsupported" ? "unsupportedTitle" : "errorTitle";
        const bodyKey = titleKey.replace("Title", "Body");
        const title = element("h1", message(titleKey));
        container.append(title, element("p", message(bodyKey)));
        if (result.asciiHostname) {
            const details = element("dl");
            for (const [key, value] of [
                ["asciiLabel", result.asciiHostname],
                ["unicodeLabel", result.unicodeHostname],
            ]) {
                const term = element("dt", message(key));
                const definition = element("dd");
                const domain = element("bdi", value);
                domain.dir = "ltr";
                definition.append(domain);
                details.append(term, definition);
            }
            container.append(details);
        }
        if (result.findings?.length) {
            const list = element("ul");
            for (const finding of result.findings) {
                const item = element("li");
                const text = finding.kind === "invalid"
                    ? `${finding.label}: ${message("invalidLabel")}`
                    : `${finding.codePoint} “${finding.character}” → “${finding.target}”`;
                const isolated = element("bdi", text);
                isolated.dir = "ltr";
                item.append(isolated);
                list.append(item);
            }
            container.append(list);
        }
        if (status === "warning") container.append(element("p", message("warningLimit"), "note"));
        container.append(element("p", message("policyNote"), "note"));
        return title;
    }

    globalThis.AntiHomographUI = Object.freeze({ message, element, render });
})();
