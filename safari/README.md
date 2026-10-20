# Anti-Homograph for Safari

[English](README.md) | [日本語](README-ja.md)

A macOS Safari Web Extension that warns when a domain contains a non-ASCII
character mapped entirely to ASCII letters by Unicode 17.0.0. It uses the
same 1,407 mappings as the Unbound filter, including single-script names,
subdomains, TLDs, and multi-letter targets. `аmazon.com` triggers a warning;
`amazon.com`, `bücher.de`, and `日本語.jp` do not.

**This is a warning tool, not a navigation or phishing blocker.** A warning
banner appears in the top-level HTTP/HTTPS page. The toolbar popup independently
checks the current address and shows its Punycode, Unicode display, code points,
and ASCII look-alikes. “Leave this page” replaces it with `about:blank`;
dismissing a banner lasts only for that document and creates no allowlist.

## Try it in macOS Safari

The extension folder is ready to load; it has no npm dependencies or build step.
The initial development target is macOS Safari 27. Older Safari releases and
iOS have not been verified.

On Safari versions that offer **Settings > Developer > Add Temporary Extension**,
select `safari/extension`. Follow Safari's unsigned-extension authentication
prompt, enable the extension, and allow access to the websites you want checked.
Temporary extensions are removed when Safari quits or after 24 hours.

To package it as a macOS app instead, install Xcode and run from the repository root:

```sh
python3 scripts/fetch_confusables.py
sh scripts/package_safari.sh
xcodebuild -project build/safari/AntiHomograph/AntiHomograph.xcodeproj \
  -scheme AntiHomograph -configuration Debug \
  -derivedDataPath build/safari-derived CODE_SIGNING_ALLOWED=NO build
```

The script refuses to overwrite an existing generated project. Extension resources
are referenced from `safari/extension`, so ordinary edits require only rebuilding.
Adding or removing resource files requires regenerating the project.
Open the generated project in Xcode and run its app to register the extension.
Use your own bundle identifier/team when signing for distribution. For unsigned
local development, follow Apple's instructions for enabling unsigned extensions;
the repository does not change Safari settings, install the app, or enable it.

Website access is essential for automatic banners. Enable it on **all websites**
for broad coverage, or on selected sites for limited coverage. Merely installing
the extension does not grant access. The popup's `activeTab` permission permits
a check after clicking the toolbar button; it does not establish that automatic
warnings are enabled everywhere. Check Safari profile and private-browsing
permissions separately.

## Detection and privacy boundaries

No network requests, telemetry, background script, cookies, browsing-history
storage, or saved exceptions are used. Only the current page's hostname is
classified; URL paths and query parameters are not shown or stored.
All code and Unicode data ship with the extension.

The page can start loading or executing before a banner appears. A malicious
website can remove, cover, or imitate an in-page banner, even though its styles
are isolated in a closed Shadow DOM. Use the Safari toolbar popup for an
extension-owned result. This does not inspect linked URLs, frames, subresources,
CNAMEs, or downloads and does not protect other applications. Safari-restricted
pages and sites without granted access cannot show automatic banners.

Legitimate names can trigger warnings. A “no matching characters” result is
not a safety verdict. ASCII-only look-alikes, many accented letters, and other
forms of phishing remain outside this policy. Safari's URL parser can reject
or normalize a name before this extension sees it. Remaining malformed or
non-canonical Punycode is reported as a warning; this is not full IDNA validation.

## Develop and check the shared policy

```sh
python3 scripts/fetch_confusables.py
python3 scripts/build_safari_data.py
python3 scripts/build_safari_data.py --check
node --test tests/safari.test.cjs
```

Use Node.js 22 or newer and Python 3. The generator verifies the pinned checksum
and reuses `parse_confusables` from the Python filter. Commit the generated
`confusables.js` when changing the Unicode version. Tests compare the JavaScript
classifier against Python for every mapping and additional labels, then exercise
warning/popup logic with a small DOM/API test double. They do not simulate Safari
permissions or establish VoiceOver behavior.

On macOS, run `swift tests/safari_webkit.swift` for real WebKit DOM, rendering,
focus, and dismissal checks. It stubs the extension APIs, makes no test-site
requests, and writes screenshots under `build/safari-webkit`. This does not
install or enable a Safari extension.

The original PNG shield artwork can be regenerated on macOS with
`swift scripts/build_safari_icons.swift`. Unicode data is separately licensed;
keep both `extension/LICENSE.txt` and `extension/UNICODE-LICENSE.txt` when packaging.

Development evidence on 2026-10-20: unsigned macOS app built with Xcode 27.1
on macOS 27.0.1; all 1,407 mappings and 407 additional labels matched Python;
seven WebKit scenarios covered English/Japanese, light/dark, 200% zoom, focus
and dismissal. Screenshots were inspected. Safari 27.0.1 is installed, but
extension registration, Safari permissions, real keyboard traversal, and
VoiceOver have not been exercised. No distribution signing has been performed.

Before release, test installation and website access in Safari, the Unicode and
Punycode address variants, both banner actions, denied permissions, profiles,
private browsing, dark appearance, keyboard access, 200% zoom, and VoiceOver.
Automatic banners intentionally do not steal focus or show modal dialogs.
Text conveys the warning without depending on color. There is no animation.
The Web UI uses semantic HTML; it is not a native macOS alert.

## Research and primary references

On 2026-10-20, searches of the web, Mac App Store, and public GitHub projects
did not identify a Safari extension dedicated to this warning. That is a scoped
search result, not proof that none exists. An existing Chrome alternative is
[Unicode Domain Warning](https://chromewebstore.google.com/detail/unicode-domain-warning/khijgpndoffkmanglickjbnkbjimcdhn).

Apple sources retrieved 2026-10-20:

| Source | Application |
| --- | --- |
| [Creating a Safari web extension](https://developer.apple.com/documentation/safariservices/creating-a-safari-web-extension) | APPLE-SDK: extension resources and toolbar popup |
| [Packaging a web extension for Safari](https://developer.apple.com/documentation/safariservices/packaging-a-web-extension-for-safari) | APPLE-SDK: Xcode packager, formerly converter |
| [Running your Safari web extension](https://developer.apple.com/documentation/safariservices/running-your-safari-web-extension) | APPLE-SDK: temporary installation, signing and website access |
| [Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos) | APPLE-HIG: keyboard and pointer use |
| [Alerts](https://developer.apple.com/design/human-interface-guidelines/alerts) | APPLE-HIG: specific warning text and actionable labels; no native-alert claim |
| [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility) | APPLE-HIG: text, contrast and adaptation |

The design is deliberately small: one warning, explicit domain evidence, a
safe exit, a document-only dismissal, and an independent toolbar result.
Japanese and English follow Safari's UI language; light/dark appearance follows
the system. No external fonts, assets, frameworks, or services are required.
