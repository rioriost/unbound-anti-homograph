# Rebuild the vendor RPM instead of dropping security backports

This is the build recipe used for the RHEL 10.2 deployment on 2026-10-16.
The vendor source was `unbound-1.24.2-7.el10_2.6.src.rpm`; the resulting
release was `1.24.2-7.el10_2.6.antihomograph1`. This is a reference snapshot,
not a recommendation to install that version after newer security releases
become available.

The callback fix itself belongs to the separate
[Unbound project](https://github.com/rioriost/unbound). It is not included here.
You must first obtain its reviewed fix commit, including the native capability
marker. Set `CORE_SOURCE` to that local checkout and `CORE_COMMIT` to the fix
commit. Do not build from an unpatched default branch.

Use a matching RHEL build environment, preferably a separate builder. If
building on the resolver, keep the old service running and limit build jobs.
Do not build as root. The commands below require an entitled RHEL installation
and the vendor source repositories. Build dependencies are installed with root
privileges, but the source/RPM build is not.

```sh
set -eu
: "${CORE_SOURCE:?Set the reviewed Unbound checkout path}"
: "${CORE_COMMIT:?Set the reviewed callback-fix commit}"
project=$(pwd)
topdir=$(mktemp -d "$HOME/unbound-rpmbuild.XXXXXXXX")
mkdir -p "$topdir/SOURCES" "$topdir/SPECS" "$topdir/download"

sudo dnf download --source --destdir "$topdir/download" \
    unbound-1.24.2-7.el10_2.6
sudo chown "$(id -u):$(id -g)" \
    "$topdir/download/unbound-1.24.2-7.el10_2.6.src.rpm"
rpm -K "$topdir/download/unbound-1.24.2-7.el10_2.6.src.rpm"
rpm -i --define "_topdir $topdir" \
    "$topdir/download/unbound-1.24.2-7.el10_2.6.src.rpm"

sudo dnf --enablerepo=codeready-builder-for-rhel-10-x86_64-rpms \
    builddep "$topdir/download/unbound-1.24.2-7.el10_2.6.src.rpm"

git -C "$CORE_SOURCE" diff "$CORE_COMMIT^" "$CORE_COMMIT" \
    --src-prefix=a/unbound-1.24.2/ --dst-prefix=b/unbound-1.24.2/ \
    -- pythonmod/interface.i util/data/msgreply.c \
    > "$topdir/SOURCES/unbound-vendor-veto.patch"
test -s "$topdir/SOURCES/unbound-vendor-veto.patch"
patch --directory="$topdir/SPECS" -p0 \
    < "$project/config/rhel-1.24.2.spec.patch"

nice -n 10 rpmbuild --define "_topdir $topdir" \
    --define "dist .el10_2" --define "_smp_mflags -j2" \
    -ba "$topdir/SPECS/unbound.spec"
```

The extra source-path component matches the vendor spec's `%autopatch -p2`.
The explicit `dist .el10_2` matters: the local default may be `.el10`, which
would not preserve the installed vendor release's RPM ordering.
All vendor patches, compiler/hardening flags, build features, package
dependencies, and `%check` tests remain in the spec. The change is only the
release suffix and one additional core patch.

Review the diff and complete build/test log. Keep the source RPM, core patch,
modified spec, checksums, and binary RPMs for audit/rollback. Verify the core
patch still applies correctly when updating vendor sources; do not reuse this
version-specific spec patch blindly.

Before installation, extract the `unbound` and `python3-unbound` RPMs into an
isolated directory and run the native tests from the main README with the
extracted binary and generated wrapper on `PYTHONPATH`. The `unbound-control`
binary must be alongside Unbound. Then retain the matching original signed
binary RPMs for rollback and review a `dnf --assumeno` transaction.

This deployment upgraded only the already-installed `unbound`, `unbound-libs`,
and `unbound-anchor` packages and added their matching `python3-unbound`.
Install that exact set together, not every generated RPM: development,
debug, utilities, and dracut subpackages are not required by the filter.
Package hooks can restart services, so perform installation in the approved
change window, confirm the original configuration was preserved, and only
then continue with filter activation.

Automatic security updates can replace this custom build with a stock one.
The filter then stops startup instead of allowing a bypass. Integrate native
preflight/rebuilds into the update process and monitor DNS availability; do not
disable all security updates or leave a custom security build unmaintained.
