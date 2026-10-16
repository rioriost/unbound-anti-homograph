"""Reject IDN labels containing non-ASCII confusables of ASCII letters."""

import codecs
import os


PUNYCODE = codecs.lookup("punycode")
ASCII_CONFUSABLES = None


def parse_confusables(lines):
    mappings = {}
    for number, line in enumerate(lines, 1):
        entry = line.partition("#")[0].strip()
        if not entry:
            continue
        fields = entry.split(";")
        if len(fields) != 3 or fields[2].strip() != "MA":
            raise ValueError("invalid confusables entry at line {}".format(number))
        source = chr(int(fields[0].strip(), 16))
        target = "".join(chr(int(value, 16)) for value in fields[1].split())
        if not target:
            raise ValueError("empty confusables target at line {}".format(number))
        if ord(source) > 127 and all(
            "A" <= character <= "Z" or "a" <= character <= "z"
            for character in target
        ):
            mappings[source] = target
    if not mappings:
        raise ValueError("confusables data contains no ASCII-letter mappings")
    return mappings


def block_reason(wire_name, mappings):
    offset = 0
    while offset < len(wire_name):
        length = wire_name[offset]
        offset += 1
        if length == 0:
            return None if offset == len(wire_name) else "invalid DNS name"
        if length > 63 or offset + length >= len(wire_name):
            return "invalid DNS label length"
        label = wire_name[offset:offset + length].lower()
        offset += length
        if not label.startswith(b"xn--"):
            continue
        payload = label[4:]
        try:
            decoded = PUNYCODE.decode(payload, "strict")[0]
            encoded = PUNYCODE.encode(decoded, "strict")[0]
        except UnicodeError:
            return "invalid Punycode label"
        if encoded != payload or not any(ord(character) > 127 for character in decoded):
            return "non-canonical Punycode label"
        for character in decoded:
            if character in mappings:
                return "U+{:04X} confusable with {!r}".format(
                    ord(character), mappings[character]
                )
    return "unterminated DNS name"


def query_block_reason(qinfo):
    if ASCII_CONFUSABLES is None:
        raise RuntimeError("homograph filter has not been initialized")
    reason = block_reason(qinfo.qname, ASCII_CONFUSABLES)
    if reason:
        log_info("homograph: refusing {}: {}".format(qinfo.qname_str, reason))
    return reason


def inplace_reply(qinfo, qstate, rep, rcode, edns, opt_list_out, region, **kwargs):
    # Callback failures discard cached answers and turn positive local replies
    # into SERVFAIL, without modifying shared cached response objects.
    if qinfo is None or rcode != RCODE_NOERROR:
        return True
    return query_block_reason(qinfo) is None


def init_standard(id, env):
    global ASCII_CONFUSABLES
    # pythonmod ignores False returns; only exceptions abort module startup.
    if not globals().get("INPLACE_REPLY_VETO_SUPPORTED", False):
        message = "homograph: Unbound lacks the required inplace-reply-veto patch"
        log_err(message)
        raise RuntimeError(message)
    data_path = os.path.join(os.path.dirname(mod_env["script"]), "confusables.txt")
    try:
        with open(data_path, encoding="utf-8") as source:
            ASCII_CONFUSABLES = parse_confusables(source)
    except (OSError, ValueError, UnicodeError) as error:
        message = "homograph: cannot load {}: {}".format(data_path, error)
        log_err(message)
        raise RuntimeError(message) from error
    for name, register in (
        ("reply", register_inplace_cb_reply),
        ("cache", register_inplace_cb_reply_cache),
        ("local", register_inplace_cb_reply_local),
    ):
        if not register(inplace_reply, env, id):
            message = "homograph: cannot register {} callback".format(name)
            log_err(message)
            raise RuntimeError(message)
    log_info("homograph: loaded {} ASCII-letter confusables".format(len(ASCII_CONFUSABLES)))
    return True


def deinit(id):
    return True


def inform_super(id, qstate, superqstate, qdata):
    return True


def operate(id, event, qstate, qdata):
    if event in (MODULE_EVENT_NEW, MODULE_EVENT_PASS):
        if query_block_reason(qstate.qinfo):
            qstate.return_msg = None
            qstate.return_rcode = RCODE_REFUSED
            qstate.no_cache_store = 1
            qstate.ext_state[id] = MODULE_FINISHED
        else:
            qstate.ext_state[id] = MODULE_WAIT_MODULE
        return True
    if event == MODULE_EVENT_MODDONE:
        qstate.ext_state[id] = MODULE_FINISHED
        return True
    log_err("homograph: unexpected module event {}".format(event))
    qstate.ext_state[id] = MODULE_ERROR
    return True
