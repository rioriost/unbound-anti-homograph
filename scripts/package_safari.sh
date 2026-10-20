#!/bin/sh
# Generate a local macOS host app without changing Safari or signing settings.
set -eu
cd "$(dirname "$0")/.."
python3 scripts/build_safari_data.py --check
if [ -e build/safari/AntiHomograph ]; then
    printf '%s\n' 'build/safari/AntiHomograph already exists; build its Xcode project or move it before regenerating.' >&2
    exit 1
fi
mkdir -p build/safari
xcrun safari-web-extension-converter safari/extension \
    --project-location build/safari \
    --app-name AntiHomograph \
    --bundle-identifier io.github.rioriost.AntiHomograph \
    --macos-only --swift --no-open --no-prompt
