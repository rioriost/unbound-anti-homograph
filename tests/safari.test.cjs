const assert = require("node:assert/strict");
const { readFileSync, existsSync } = require("node:fs");
const { join, resolve } = require("node:path");
const { spawnSync } = require("node:child_process");
const { test } = require("node:test");
const vm = require("node:vm");

const root = resolve(__dirname, "..");
const extension = join(root, "safari/extension");
const read = name => readFileSync(join(extension, name), "utf8");

function context(extra = {}) {
    const sandbox = vm.createContext({ URL, TypeError, console, ...extra });
    for (const file of ["confusables.js", "detector.js"]) {
        vm.runInContext(read(file), sandbox, { filename: file });
    }
    return sandbox;
}

const detector = context().AntiHomograph;

test("matches Unbound on every pinned mapping and diverse nonmatching labels", () => {
    const fixtures = spawnSync("python3", ["-c", `
import importlib.util, json, random
from pathlib import Path
root = Path.cwd()
spec = importlib.util.spec_from_file_location("policy", root / "files/homograph_filter.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
mappings = policy.parse_confusables((root / "files/confusables.txt").read_text().splitlines())
labels = list(mappings) + ["amazon", "bücher", "日本語", "αβγ", "аmazon", "аррӏе", "例え"]
random.seed(17)
scalars = [chr(n) for n in range(128, 0x20000) if not 0xd800 <= n <= 0xdfff]
labels += ["".join(random.choices(scalars, k=random.randrange(1, 12))) for _ in range(400)]
cases = []
for label in labels:
    ace = "xn--" + label.encode("punycode").decode() if not label.isascii() else label
    wire = bytes([len(ace)]) + ace.encode() + b"\\x07example\\x00"
    cases.append([ace + ".example", policy.block_reason(wire, mappings) is not None, label])
print(json.dumps(cases))
`], { cwd: root, encoding: "utf8" });
    assert.equal(fixtures.status, 0, fixtures.stderr);
    const cases = JSON.parse(fixtures.stdout);
    assert.ok(cases.length > 1800);
    for (const [hostname, blocked, unicode] of cases) {
        const result = detector.analyzeHostname(hostname);
        assert.equal(result.status, blocked ? "warning" : "clear", hostname);
        assert.equal(result.unicodeHostname, unicode + ".example", hostname);
    }
});

test("checks single-script labels, subdomains, TLDs, case, and terminal dots", () => {
    for (const hostname of [
        "xn--80ak6aa92e.com", "xn--mazon-3ve.com", "www.xn--mazon-3ve.com",
        "example.xn--80a", "XN--MAZON-3VE.COM.", "xn--cfa.example",
        "xn--w6j.example", "xn--bh2d.example",
    ]) {
        assert.equal(detector.analyzeHostname(hostname).status, "warning", hostname);
    }
    for (const hostname of ["amazon.com", "rnazon.com", "xn--bcher-kva.de", "xn--wgv71a119e.jp"]) {
        assert.equal(detector.analyzeHostname(hostname).status, "clear", hostname);
    }
});

test("malformed and noncanonical Punycode is a warning, never an all-clear", () => {
    for (const label of ["xn--", "xn--abc-", "xn--!", "xn--a-", "xn--99999999999999999999",
        "xn--" + "z".repeat(64)]) {
        const result = detector.analyzeHostname(label + ".example");
        assert.equal(result.status, "warning", label);
        assert.equal(result.findings[0].kind, "invalid", label);
    }
});

test("uses the URL hostname, not userinfo, query, path, or a domain suffix guess", () => {
    assert.equal(detector.analyzeURL("https://аmazon.com/path").status, "warning");
    assert.equal(detector.analyzeURL("https://аmazon.com@amazon.com/xn--80a").status, "clear");
    assert.equal(detector.analyzeURL("https://amazon.com/?next=https://аmazon.com").status, "clear");
    assert.equal(detector.analyzeURL("http://[::1]:8080").status, "clear");
    assert.equal(detector.analyzeURL("https://日本語.jp").status, "clear");
    for (const url of ["about:blank", "file:///tmp/test", "data:text/html,hello", "javascript:alert(1)"]) {
        assert.equal(detector.analyzeURL(url).status, "unsupported");
    }
    assert.equal(detector.analyzeURL("not a URL").status, "error");
});

test("missing policy is an explicit error", () => {
    assert.throws(() => vm.runInNewContext(read("detector.js")), /Unicode policy/);
});

class Element {
    constructor(tag) {
        this.tagName = tag;
        this.children = [];
        this.attributes = {};
        this.style = {};
        this.dataset = {};
        this.listeners = {};
        this.textContent = "";
    }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; this.textContent = ""; }
    setAttribute(key, value) { this.attributes[key] = value; }
    attachShadow(options) {
        this.shadowMode = options.mode;
        this.testShadow = new Element("shadow-root");
        return this.testShadow;
    }
    addEventListener(event, listener) { this.listeners[event] = listener; }
    remove() { this.removed = true; }
    get innerHTML() { throw new Error("HTML parsing is prohibited"); }
    set innerHTML(_) { throw new Error("HTML parsing is prohibited"); }
}

function uiContext({ url = "https://аmazon.com", locale = "en", queryError,
    tab = { url }, framed = false, hasRoot = true } = {}) {
    const messages = JSON.parse(read(`_locales/${locale}/messages.json`));
    const document = {
        documentElement: hasRoot ? new Element("html") : null,
        createElement: tag => new Element(tag),
        getElementById: () => document.result,
        result: new Element("main"),
    };
    const window = {};
    window.top = framed ? {} : window;
    const location = { href: url, replace(value) { this.replaced = value; } };
    const observer = {};
    const sandbox = context({
        document, window, location,
        browser: {
            i18n: {
                getMessage: key => {
                    assert.ok(messages[key], `Missing ${locale} message: ${key}`);
                    return messages[key].message;
                },
                getUILanguage: () => locale,
            },
            tabs: { query: async () => {
                if (queryError) throw queryError;
                return tab ? [tab] : [];
            } },
        },
        console: { error: (...args) => { sandbox.loggedError = args; } },
        MutationObserver: class {
            constructor(callback) { observer.callback = callback; }
            observe() { observer.observing = true; }
            disconnect() { observer.disconnected = true; }
        },
    });
    vm.runInContext(read("ui.js"), sandbox);
    return { sandbox, document, location, observer };
}

function descendants(node) {
    return [node, ...node.children.flatMap(descendants)];
}

test("top-frame warning mounts at document_start, with isolated text and working actions", () => {
    for (const locale of ["en", "ja"]) {
        const { sandbox, document, location } = uiContext({ locale });
        vm.runInContext(read("content.js"), sandbox);
        const [host] = document.documentElement.children;
        assert.equal(host.shadowMode, "closed");
        const nodes = descendants(host.testShadow);
        assert.ok(nodes.some(node => node.attributes.role === "alert"));
        const buttons = nodes.filter(node => node.tagName === "button");
        assert.equal(buttons.length, 2);
        buttons[1].listeners.click();
        assert.equal(location.replaced, "about:blank");
        buttons[0].listeners.click();
        assert.equal(host.removed, true);
        assert.ok(nodes.some(node => node.tagName === "bdi" && node.dir === "ltr"));
    }
});

test("banner waits for the document element and disconnects its observer", () => {
    const { sandbox, document, observer } = uiContext({ hasRoot: false });
    vm.runInContext(read("content.js"), sandbox);
    assert.equal(observer.observing, true);
    document.documentElement = new Element("html");
    observer.callback();
    assert.equal(document.documentElement.children.length, 1);
    assert.equal(observer.disconnected, true);
});

test("no injected UI on an allowed page or in a subframe", () => {
    for (const options of [{ url: "https://amazon.com" }, { framed: true }]) {
        const { sandbox, document } = uiContext(options);
        vm.runInContext(read("content.js"), sandbox);
        assert.equal(document.documentElement.children.length, 0);
    }
});

test("toolbar popup handles warning, clear, unsupported, unavailable URL, and errors", async () => {
    for (const [options, expected] of [
        [{}, "warning"],
        [{ url: "https://amazon.com" }, "clear"],
        [{ url: "about:blank" }, "unsupported"],
        [{ tab: {} }, "error"],
        [{ tab: null }, "error"],
        [{ queryError: new Error("permission denied") }, "error"],
    ]) {
        const { sandbox, document } = uiContext(options);
        await vm.runInContext(read("popup.js"), sandbox);
        assert.equal(document.result.dataset.status, expected);
        assert.equal(document.result.attributes["aria-busy"], "false");
        assert.equal(document.documentElement.lang, "en");
        if (options.queryError) assert.ok(sandbox.loggedError);
    }
});

test("manifest has only the required access, local resources, and complete locales", () => {
    const manifest = JSON.parse(read("manifest.json"));
    assert.deepEqual(manifest.permissions, ["activeTab"]);
    assert.equal(manifest.background, undefined);
    assert.equal(manifest.web_accessible_resources, undefined);
    assert.equal(manifest.content_scripts[0].all_frames, false);
    for (const file of [
        ...manifest.content_scripts[0].js, manifest.action.default_popup,
        ...Object.values(manifest.icons), ...Object.values(manifest.action.default_icon),
    ]) {
        assert.ok(existsSync(join(extension, file)), file);
    }
    const english = JSON.parse(read("_locales/en/messages.json"));
    const japanese = JSON.parse(read("_locales/ja/messages.json"));
    assert.deepEqual(Object.keys(english).sort(), Object.keys(japanese).sort());
    for (const messages of [english, japanese]) {
        for (const entry of Object.values(messages)) assert.ok(entry.message.trim());
    }
    assert.equal(read("LICENSE.txt"), readFileSync(join(root, "LICENSE"), "utf8"));
    assert.equal(read("UNICODE-LICENSE.txt"), readFileSync(join(root, "LICENSES/Unicode-3.0.txt"), "utf8"));
});
