// Run on macOS: swift tests/safari_webkit.swift
// Exercises the real WebKit DOM with a stub of Safari's extension APIs.
import AppKit
import WebKit

@MainActor
final class SafariWebKitChecks: NSObject, WKNavigationDelegate {
    struct Scenario {
        let name: String
        let url: String
        let locale: String
        let dark: Bool
        let zoom: CGFloat
        let banner: Bool
        let status: String
    }

    let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    let scenarios = [
        Scenario(name: "warning-en", url: "https://xn--mazon-3ve.com",
                 locale: "en", dark: false, zoom: 1, banner: false, status: "warning"),
        Scenario(name: "warning-ja-dark", url: "https://xn--80ak6aa92e.com",
                 locale: "ja", dark: true, zoom: 1, banner: false, status: "warning"),
        Scenario(name: "warning-ja-zoom", url: "https://xn--mazon-3ve.com",
                 locale: "ja", dark: false, zoom: 2, banner: false, status: "warning"),
        Scenario(name: "clear", url: "https://xn--wgv71a119e.jp",
                 locale: "en", dark: false, zoom: 1, banner: false, status: "clear"),
        Scenario(name: "unsupported", url: "about:blank",
                 locale: "en", dark: false, zoom: 1, banner: false, status: "unsupported"),
        Scenario(name: "banner-ja", url: "https://xn--mazon-3ve.com",
                 locale: "ja", dark: false, zoom: 1, banner: true, status: "warning"),
        Scenario(name: "banner-ja-dark-zoom", url: "https://xn--mazon-3ve.com",
                 locale: "ja", dark: true, zoom: 2, banner: true, status: "warning"),
    ]
    var index = 0
    var webView: WKWebView!
    var window: NSWindow!

    func source(_ name: String) throws -> String {
        try String(contentsOf: root.appendingPathComponent("safari/extension/\(name)"), encoding: .utf8)
    }

    func startNext() {
        guard index < scenarios.count else {
            print("PASS: \(scenarios.count) WebKit rendering/interaction scenarios")
            NSApplication.shared.terminate(nil)
            return
        }
        do {
            let scenario = scenarios[index]
            let messages = try source("_locales/\(scenario.locale)/messages.json")
            let prelude = """
                globalThis.browser = {
                    i18n: {
                        getMessage: key => (\(messages))[key].message,
                        getUILanguage: () => "\(scenario.locale)"
                    },
                    tabs: { query: async () => [{ url: "\(scenario.url)" }] }
                };
                """
            let configuration = WKWebViewConfiguration()
            configuration.userContentController.addUserScript(WKUserScript(
                source: prelude, injectionTime: .atDocumentStart, forMainFrameOnly: true
            ))
            if scenario.banner {
                let scripts = try ["confusables.js", "detector.js", "ui.js", "content.js"]
                    .map { try source($0) }.joined(separator: "\n")
                configuration.userContentController.addUserScript(WKUserScript(source: """
                    const originalAttachShadow = Element.prototype.attachShadow;
                    Element.prototype.attachShadow = function(options) {
                        globalThis.testShadowRoot = originalAttachShadow.call(this, options);
                        return globalThis.testShadowRoot;
                    };
                    \(scripts)
                    """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
            }
            let frame = NSRect(x: 0, y: 0, width: scenario.banner ? 800 : 360, height: 900)
            webView = WKWebView(frame: frame, configuration: configuration)
            webView.navigationDelegate = self
            webView.pageZoom = scenario.zoom
            webView.appearance = NSAppearance(named: scenario.dark ? .darkAqua : .aqua)
            if window == nil {
                window = NSWindow(contentRect: frame, styleMask: [], backing: .buffered, defer: false)
            }
            window.setContentSize(frame.size)
            window.contentView = webView
            if scenario.banner {
                webView.loadHTMLString(
                    "<!doctype html><html><body><p>Local test page. No network request.</p></body></html>",
                    baseURL: URL(string: scenario.url)
                )
            } else {
                let folder = root.appendingPathComponent("safari/extension")
                webView.loadFileURL(folder.appendingPathComponent("popup.html"), allowingReadAccessTo: folder)
            }
        } catch {
            fail(error.localizedDescription)
        }
    }

    func fail(_ reason: String) -> Never {
        fputs("FAIL \(scenarios[index].name): \(reason)\n", stderr)
        exit(1)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        let scenario = scenarios[index]
        let checks = scenario.banner ? """
            const root = globalThis.testShadowRoot;
            if (!root) throw new Error("Missing banner");
            if (!root.querySelector('[role="alert"]')) throw new Error("Missing warning semantics");
            if (root.querySelectorAll("button").length !== 2) throw new Error("Missing actions");
            if (root.querySelector("section").lang !== "\(scenario.locale)") throw new Error("Wrong language");
            const button = root.querySelector("button");
            button.focus();
            if (root.activeElement !== button) throw new Error("Button cannot receive focus");
            const host = root.host;
            const box = host.getBoundingClientRect();
            if (box.width > innerWidth + 1 || box.height > innerHeight * .71) {
                throw new Error("Banner is outside viewport bounds");
            }
            if (root.querySelector("section").scrollWidth > host.clientWidth + 1) {
                throw new Error("Banner overflows horizontally");
            }
            """ : """
            const result = document.querySelector("#result");
            if (result.dataset.status !== "\(scenario.status)") throw new Error("Wrong status: " + result.dataset.status);
            if (result.getAttribute("aria-busy") !== "false") throw new Error("Popup is still loading");
            if (document.documentElement.lang !== "\(scenario.locale)") throw new Error("Wrong language");
            if (document.documentElement.scrollWidth > innerWidth + 1) throw new Error("Horizontal overflow");
            if (!result.querySelector("h1")) throw new Error("Missing heading");
            """
        webView.evaluateJavaScript("(() => { \(checks); return true; })()") { _, error in
            if let error { self.fail(error.localizedDescription) }
            let output = self.root.appendingPathComponent("build/safari-webkit", isDirectory: true)
            do {
                try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            } catch { self.fail(error.localizedDescription) }
            webView.takeSnapshot(with: nil) { image, error in
                guard let image, let tiff = image.tiffRepresentation,
                      let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:])
                else { self.fail(error?.localizedDescription ?? "Snapshot unavailable") }
                do {
                    try png.write(to: output.appendingPathComponent("\(scenario.name).png"))
                } catch { self.fail(error.localizedDescription) }
                if scenario.banner {
                    webView.evaluateJavaScript("""
                        globalThis.testShadowRoot.querySelector("button").click();
                        !globalThis.testShadowRoot.host.isConnected;
                        """) { removed, error in
                        if error != nil || (removed as? Bool) != true { self.fail("Dismissal failed") }
                        self.finishScenario()
                    }
                } else {
                    self.finishScenario()
                }
            }
        }
    }

    func finishScenario() {
        print("PASS: \(scenarios[index].name)")
        index += 1
        startNext()
    }
}

MainActor.assumeIsolated {
    let app = NSApplication.shared
    app.setActivationPolicy(.prohibited)
    let checks = SafariWebKitChecks()
    checks.startNext()
    DispatchQueue.main.asyncAfter(deadline: .now() + 60) {
        fputs("FAIL: WebKit checks timed out\n", stderr)
        exit(1)
    }
    app.run()
}
