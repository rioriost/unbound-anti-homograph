# Unbound anti-homograph filter

Reject DNS queries whose IDN labels contain non-ASCII characters mapped to
ASCII letters by Unicode's confusables table. This is a deliberately strict
character policy, not a comparison against a list of protected brands.

**A patched, Python-enabled Unbound is required. Stock Unbound is not sufficient.**
The filter checks a native capability marker and refuses to initialize on an
unsupported build. Read the prerequisites before changing a live resolver.

## What is blocked

Every case-insensitive `xn--` label in the queried name is decoded as Punycode.
If any decoded non-ASCII character maps entirely to `A-Z` or `a-z`, the query
is rejected. Multi-letter mappings such as `rn` count too. Mixed scripts are
not required: single-script labels, subdomains, and TLDs are all checked.
Malformed or non-canonical Punycode labels are also rejected.

| Name | Filter decision |
| --- | --- |
| `amazon.com` | Allow |
| `аmazon.com` (Cyrillic U+0430; `xn--mazon-3ve.com`) | Block |
| `ı.example` (Latin dotless i, U+0131) | Block |
| `〇.example` (ideographic zero, U+3007) | Block |
| `bücher.de` / `日本語.jp` | Allow |

Unicode 17.0.0 supplies **1,407** relevant mappings. The source commit and
SHA-256 are pinned in [`scripts/fetch_confusables.py`](scripts/fetch_confusables.py).
No data is downloaded during DNS queries.

Legitimate foreign-language names containing a mapped character are blocked
too. There is no allowlist. The policy does not compare rendered fonts, remove
all accents, implement a full IDNA validator, or detect every visual spoof.
Ordinary IDN clients send Punycode A-labels; arbitrary raw UTF-8 DNS labels are
not classified by this filter.

The policy applies to the queried name, not independently to every CNAME
target in a response. It cannot control clients using another resolver, DoH,
or answers already cached on a client.

## Prerequisites: native veto support and no chroot

The required Unbound core fix is maintained separately at
[rioriost/unbound](https://github.com/rioriost/unbound). Obtain a build containing
that fix; do not assume the fork's default branch already contains it.
This repository does not modify, vendor, or publish the separate core project.

At initial publication, the production rollout used local core commit
`17b4ab1b72e1cc0e9569d51ccd7f352450bb9b04`, which had not been pushed to that
public fork. **Third-party reproduction therefore still requires the core
project's maintainer to publish the fix.** The filter and deployment materials
here are public; they are not a self-contained replacement for that dependency.

The build must provide all of the following:

- `python` in the `Linked modules:` line of `unbound -V`.
- The matching generated `unboundmodule.py`, available to embedded Python.
  Installing only libunbound's Python bindings is not sufficient.
- `INPLACE_REPLY_VETO_SUPPORTED = 1` in the embedded Python API, and actual
  propagation of failed in-place reply callbacks. A marker without the
  behavior is not sufficient; the native tests check the behavior.
- `unbound-control` next to the tested `unbound` binary. The test uses an
  isolated Unix control socket, not your production control interface.
- Python 3 and permission to run the isolated preflight under the resolver's
  nonprivileged user.

Unpatched Unbound 1.26.1 and the inspected RHEL 1.24.2 build ignore in-place
callback failure. They can return a positive cached answer despite a Python
filter's refusal. Returning `False` from Python initialization is also
insufficient to stop startup, so this filter **raises exceptions** on a
missing capability, missing/bad data, or failed callback registration.

Python initialization occurs after Unbound enters its chroot. This deployment
therefore requires explicit `chroot: ""`. This removes one isolation layer:
do not deploy this configuration where that tradeoff is unacceptable. Keep
the unprivileged service account, SELinux/AppArmor, ACLs, and other protections.

On a distribution with security backports, rebuild the exact current vendor
source package with the minimal core fix. Do not replace it with an older
generic upstream tarball just to enable Python. Rebuilding and testing the
current vendor package remains the operator's responsibility.
The [RHEL build recipe](docs/rhel-build.md) records the tested vendor-preserving
procedure and its version-specific packaging change.

## Install without replacing existing DNS settings

The following Linux/systemd example assumes the service account/group are
`unbound`, the binaries are in `/usr/sbin`, and the main configuration is
`/etc/unbound/unbound.conf`. Adapt these paths and names to your distribution.
It is a first-install procedure, not an unattended in-place upgrade.

Back up configuration, service overrides, and matching original packages
before installing a custom Unbound build. Distribution package hooks may
restart the resolver. Install the supported build and its matching Python
wrapper **before** enabling the filter.

```sh
python3 scripts/fetch_confusables.py
python3 -m unittest discover -s tests -v

sudo install -d -o root -g unbound -m 0755 /etc/unbound/homograph
sudo install -o root -g unbound -m 0644 \
    files/homograph_filter.py files/confusables.txt /etc/unbound/homograph/
sudo install -o root -g unbound -m 0644 \
    tests/test_homograph_integration.py /etc/unbound/homograph/selftest.py
```

Inspect `unbound-checkconf -o module-config /etc/unbound/unbound.conf`.
Edit a copy of [`config/homograph.conf`](config/homograph.conf) so that `python`
is prepended to the **entire existing module chain**. For example,
`respip validator iterator` must become `python respip validator iterator`.
Do not discard modules or overwrite another Python extension's configuration.
Then install the adjusted fragment:

```sh
sudo install -o root -g unbound -m 0644 \
    config/homograph.conf /etc/unbound/homograph/homograph.conf
sudo restorecon -RF /etc/unbound/homograph  # SELinux systems only
```

Do not add the include yet. Verify that no existing include/glob already loads
this directory. Script and data files must not be writable by the service user.
For subsequent upgrades, stage a separate versioned directory and test it
before switching configuration; do not overwrite files underneath an active
deployment and assume the in-memory module has been reloaded.

## Run the real resolver preflight before activation

```sh
sudo -u unbound env \
    PYTHONDONTWRITEBYTECODE=1 \
    UNBOUND_BINARY=/usr/sbin/unbound \
    UNBOUND_FILTER_SCRIPT=/etc/unbound/homograph/homograph_filter.py \
    UNBOUND_CONFUSABLES=/etc/unbound/homograph/confusables.txt \
    python3 /etc/unbound/homograph/selftest.py -v
```

This starts temporary two-thread resolvers and a local fake upstream on
unprivileged loopback ports. It does not use port 53, change your running
resolver, or send external DNS requests. It injects a previously positive
cache entry and checks that no positive answer escapes; it also checks local
answers, allowed names, malformed labels, UDP/TCP, and A/AAAA/SVCB/HTTPS/MX/TXT/ANY.
Missing or corrupt data must cause a real startup failure.

The optional unpatched-binary test is skipped unless
`UNBOUND_UNPATCHED_BINARY` is provided. Use a matching wrapper for that binary:
an uninstalled source build is detected at `<binary-directory>/pythonmod/`.
For the patched binary in an uninstalled build, set `PYTHONPATH` to its generated
`pythonmod` directory. Do not mix wrappers from different builds.

## Activate with an atomic configuration change

Record representative local A/AAAA, mail-authentication TXT, PTR, external
answers, and existing DNSSEC behavior first. Preserve existing local-data,
adblock/RPZ, forwarding, listeners, ACLs, trust anchors, and systemd overrides.
This filter neither enables nor disables DNSSEC validation.

Run the following in a shell that stops on errors. It appends only a dedicated
include; it does not regenerate your main configuration. An already-enabled
Python chain needs separate integration and will fail the chain equality check.

```sh
set -eu
sudo install -d -m 0700 /var/lib/unbound-anti-homograph
backup=$(sudo mktemp -d /var/lib/unbound-anti-homograph/rollback.XXXXXXXX)
candidate=$(sudo mktemp /etc/unbound/.homograph.XXXXXXXX)
sudo cp --preserve=all /etc/unbound/unbound.conf "$backup/unbound.conf"
sudo cp --preserve=all /etc/unbound/unbound.conf "$candidate"
printf '\ninclude: "/etc/unbound/homograph/homograph.conf"\n' |
    sudo tee -a "$candidate" > /dev/null

old_modules=$(sudo unbound-checkconf -o module-config /etc/unbound/unbound.conf)
new_modules=$(sudo unbound-checkconf -o module-config "$candidate")
test "$new_modules" = "python $old_modules"
test -z "$(sudo unbound-checkconf -o chroot "$candidate")"
sudo unbound-checkconf "$candidate"
printf 'Rollback configuration: %s/unbound.conf\n' "$backup"

sudo mv "$candidate" /etc/unbound/unbound.conf
sudo restorecon /etc/unbound/unbound.conf  # SELinux systems only
sudo systemctl restart unbound
```

`unbound-checkconf` initializes Python too: it is not merely a syntax check.
Do not use HUP/reload as a substitute for the controlled restart.

Wait for a real DNS response, not just `systemctl is-active`: a service with
`Type=simple` can be reported active before it is ready. A bounded readiness
check may retry probes, but must not silently restart the service again:

```sh
ready=false
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if response=$(dig @127.0.0.1 xn--mazon-3ve.com A +time=1 +tries=1 +noall +comments); then
        if printf '%s\n' "$response" | grep -q 'status: REFUSED'; then
            ready=true
            break
        fi
    fi
    sleep 1
done
test "$ready" = true
dig @127.0.0.1 xn--mazon-3ve.com AAAA +tcp +noall +comments
dig @127.0.0.1 amazon.com A +noall +comments +answer
```

Require `REFUSED` with zero answers for the blocked name over UDP and TCP, and
the expected normal answers for your known-good baseline. Repeat from a LAN
client and over IPv6 where used. Check the journal and MAC denials, and compare
the existing records against the pre-change baseline.

Ordinary queries and discarded cache hits return `REFUSED` (rcode 5).
An otherwise positive local-data reply returns `SERVFAIL` (rcode 2), because
that path handles the failed reply callback. Neither path returns positive
data. The filter logs the reason with the `homograph:` prefix and does not
mutate shared cached response objects.

## Roll back deliberately

If checks fail, stop the rollout and report the failure. Do not disable
SELinux or ignore errors. Restore the saved main configuration through a
same-directory temporary file, validate it, atomically replace the live file,
restore its security context, and perform an explicit recovery restart.
Check your original good-name baseline afterward.

Restoring the pre-filter main configuration removes the include and restores
its original chroot/module settings. Keeping the correctly patched binary
while removing this policy is safe. If reverting packages too, first remove
the policy; then restore matching binaries, wrapper, libraries, and companion
packages. Never leave the filter enabled with an unsupported binary.

The rollback backup contains operational configuration; keep it root-only and
do not upload it, inventory, logs, hostnames, keys, or production records here.

## Updates and license

Keep the capability guard and run the native preflight before every Unbound
update. A future stock package can replace a custom build: the guard then
stops startup rather than silently bypassing filtering. Plan rebuilds for new
vendor security updates and monitor both DNS availability and policy refusal.
Do not indefinitely pin an old security build.

Update the Unicode URL and checksum together, review changed mappings and
false positives, and rerun all tests before activation.

The original code, tests, example configuration, and documentation are
**MIT-licensed**. Unbound remains a separate BSD-3-Clause dependency and Unicode
data retains its own license; see [NOTICE](NOTICE).
