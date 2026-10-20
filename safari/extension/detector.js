(() => {
    "use strict";

    const mappings = globalThis.AntiHomographMappings;
    if (!mappings || Object.keys(mappings).length !== 1407) {
        throw new Error("Anti-Homograph: missing or incomplete Unicode policy");
    }

    // RFC 3492 Bootstring parameters for Punycode.
    const base = 36;
    const initialBias = 72;
    const initialCodePoint = 128;

    function threshold(k, bias) {
        return Math.min(26, Math.max(1, k - bias));
    }

    function adapt(delta, points, first) {
        delta = first ? Math.floor(delta / 700) : Math.floor(delta / 2);
        delta += Math.floor(delta / points);
        let k = 0;
        while (delta > 455) {
            delta = Math.floor(delta / 35);
            k += base;
        }
        return k + Math.floor(36 * delta / (delta + 38));
    }

    function checked(value) {
        if (!Number.isSafeInteger(value) || value < 0) {
            throw new RangeError("Punycode integer overflow");
        }
        return value;
    }

    function digit(character) {
        const value = character.charCodeAt(0);
        if (value >= 97 && value <= 122) return value - 97;
        if (value >= 48 && value <= 57) return value - 22;
        throw new RangeError("Invalid Punycode digit");
    }

    function encodeDigit(value) {
        return String.fromCharCode(value < 26 ? value + 97 : value + 22);
    }

    function decode(payload) {
        const output = [];
        const delimiter = payload.lastIndexOf("-");
        let position = 0;
        if (delimiter >= 0) {
            for (const character of payload.slice(0, delimiter)) {
                if (character.charCodeAt(0) > 127) {
                    throw new RangeError("Non-ASCII Punycode input");
                }
                output.push(character.charCodeAt(0));
            }
            position = delimiter + 1;
        }
        let n = initialCodePoint;
        let i = 0;
        let bias = initialBias;
        while (position < payload.length) {
            const previous = i;
            let weight = 1;
            for (let k = base; ; k += base) {
                if (position === payload.length) throw new RangeError("Truncated Punycode");
                const value = digit(payload[position++]);
                i = checked(i + checked(value * weight));
                const t = threshold(k, bias);
                if (value < t) break;
                weight = checked(weight * (base - t));
            }
            const count = output.length + 1;
            bias = adapt(i - previous, count, previous === 0);
            n = checked(n + Math.floor(i / count));
            if (n > 0x10ffff || (n >= 0xd800 && n <= 0xdfff)) {
                throw new RangeError("Invalid Unicode scalar");
            }
            i %= count;
            output.splice(i, 0, n);
            i++;
        }
        return String.fromCodePoint(...output);
    }

    function encode(text) {
        const points = Array.from(text, character => character.codePointAt(0));
        let output = points.filter(point => point < 128)
            .map(point => String.fromCharCode(point)).join("");
        let handled = output.length;
        const basic = handled;
        if (basic) output += "-";
        let n = initialCodePoint;
        let delta = 0;
        let bias = initialBias;
        while (handled < points.length) {
            const next = Math.min(...points.filter(point => point >= n));
            delta = checked(delta + checked((next - n) * (handled + 1)));
            n = next;
            for (const point of points) {
                if (point < n) delta = checked(delta + 1);
                if (point !== n) continue;
                let q = delta;
                for (let k = base; ; k += base) {
                    const t = threshold(k, bias);
                    if (q < t) break;
                    output += encodeDigit(t + (q - t) % (base - t));
                    q = Math.floor((q - t) / (base - t));
                }
                output += encodeDigit(q);
                bias = adapt(delta, handled + 1, handled === basic);
                delta = 0;
                handled++;
            }
            delta++;
            n++;
        }
        return output;
    }

    function analyzeHostname(hostname) {
        const asciiHostname = hostname.toLowerCase();
        const labels = asciiHostname.replace(/\.$/, "").split(".");
        const decodedLabels = [];
        const findings = [];
        for (const label of labels) {
            if (!label.startsWith("xn--")) {
                decodedLabels.push(label);
                continue;
            }
            let decoded;
            try {
                const payload = label.slice(4);
                if (label.length > 63 || !payload) throw new RangeError("Invalid label length");
                decoded = decode(payload);
                if (!/[^\x00-\x7f]/.test(decoded) || encode(decoded) !== payload) {
                    throw new RangeError("Non-canonical Punycode");
                }
            } catch (error) {
                if (!(error instanceof RangeError)) throw error;
                findings.push({ kind: "invalid", label });
                decodedLabels.push(label);
                continue;
            }
            decodedLabels.push(decoded);
            for (const character of new Set(decoded)) {
                if (!Object.hasOwn(mappings, character)) continue;
                findings.push({
                    kind: "confusable",
                    label,
                    character,
                    codePoint: "U+" + character.codePointAt(0).toString(16).toUpperCase().padStart(4, "0"),
                    target: mappings[character],
                });
            }
        }
        return {
            status: findings.length ? "warning" : "clear",
            asciiHostname,
            unicodeHostname: decodedLabels.join("."),
            findings,
        };
    }

    function analyzeURL(value) {
        let url;
        try {
            url = new URL(value);
        } catch (error) {
            if (!(error instanceof TypeError)) throw error;
            return { status: "error" };
        }
        if (!["http:", "https:"].includes(url.protocol) || !url.hostname) {
            return { status: "unsupported" };
        }
        return analyzeHostname(url.hostname);
    }

    globalThis.AntiHomograph = Object.freeze({ analyzeHostname, analyzeURL });
})();
