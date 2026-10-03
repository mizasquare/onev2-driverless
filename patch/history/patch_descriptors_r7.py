#!/usr/bin/env python3
"""ONEv2 descriptor patch, round 7 -- give the capture cluster a real stereo layout.

Starts from the ORIGINAL images and applies rounds 2..7 together, so this one script fully
defines the firmware. Output: *.R7.patched.bin

WHAT CHANGES, AND WHY ONLY THIS
  State before this round, all measured, not assumed:
    Windows 11  inbox usbaudio2, no vendor driver: capture + playback work, problem=0.
    macOS       capture + playback work, AND the input source popup in Audio MIDI Setup works.
    iPad USB-C  PLAYBACK ONLY. Capture never registers -- same as the untouched original, so
                this is the one goal still unmet, not a regression we introduced.

  With both AudioStreaming interfaces now dumped field by field, exactly two things differ
  between the direction that works on iPad and the direction that does not:

      playback (iface 1)                  capture (iface 2)
      bmChannelConfig 0x00000003          bmChannelConfig 0x00000000   <-- this round
      IT 2 -> FU 4 -> OT 3                IT 9/11/13 -> SU 15 -> FU 10 -> OT 8

  The zero came from round 3: the original declared 0x04 (FRONT_CENTER alone) on a 2-channel
  cluster, which is self-contradictory, and I zeroed it. Zero is legal -- ADC-2 reads it as
  "no defined spatial location" -- and both Windows and macOS accept it. iOS is markedly
  stricter about channel layouts, and 0x03 (FRONT_LEFT | FRONT_RIGHT) is the value the playback
  side already carries through every host including the iPad. So this round makes the capture
  cluster say what the hardware actually is, a stereo pair, in the same words playback uses:

      capture AS_GENERAL   bmChannelConfig 0x00000000 -> 0x00000003
      INPUT_TERMINAL 9     bmChannelConfig 0x00000000 -> 0x00000003   (internal mic + instrument)
      INPUT_TERMINAL 11    bmChannelConfig 0x00000000 -> 0x00000003   (external mic + instrument)
      INPUT_TERMINAL 13    bmChannelConfig 0x00000000 -> 0x00000003   (external 48V + instrument)

  Cost: zero bytes. bmChannelConfig is a fixed 4-byte field that is already there, so the
  descriptor stays 328 bytes and nothing moves. Risk: low -- the value is the one the playback
  chain has always used, and the three terminals feed a selector whose pins must all carry the
  same cluster, which this keeps true.

  This is a HYPOTHESIS about iOS, and it is the cheapest one that fits the evidence. If the iPad
  still refuses capture, the next suspect is the selector unit itself: iOS may not implement
  Selector Units, in which case the capture path has to be describable without one. That change
  would cost Windows and macOS their input switching, so it belongs in a separate experimental
  image, not here.

Also carried: round 2 (IAD 4->3, drop the duplicate CLOCK_SOURCE), round 3 (clock bmAttributes
0x03, iso OUT Adaptive, iso IN Async), round 4 (three mic feature units collapsed into one
2-channel unit after the selector, playback FU widened to 18), round 5 (that unit advertises no
controls), round 6 (SELECTOR_UNIT iSelector 21 -> 0, string 21 does not exist), and bcdDevice
-> 1.10 plus the copy-B bMaxPower marker.
"""
import os, struct

FWDIR = os.path.join(os.path.dirname(__file__), "..", "firmware")
OUTDIR = FWDIR          # patched images land next to the stock ones, in firmware/
CFG_SIG = bytes.fromhex("09025401040100c005")
DEV_SIG = bytes.fromhex("600c17000501")
SLOT = 340

AC_HEADER, IN_TERM, OUT_TERM, MIXER, SELECTOR, FEATURE, CLOCK_SRC = 1, 2, 3, 4, 5, 6, 0x0a


# ------------------------------------------------- split / join a config descriptor
def split(cfg):
    """Config descriptor bytes -> list of descriptor bytearrays."""
    out, p = [], 0
    while p < len(cfg) and cfg[p]:
        out.append(bytearray(cfg[p:p + cfg[p]]))
        p += cfg[p]
    return out


def join(items):
    return b"".join(bytes(i) for i in items)


def is_cs(d, subtype, in_ac):
    return d[1] == 0x24 and d[2] == subtype


def ac_span(items):
    """Indices of the class-specific AudioControl descriptors (AC_HEADER .. last 0x24 before
    the first endpoint)."""
    first = last = None
    for i, d in enumerate(items):
        if d[1] == 0x24 and d[2] == AC_HEADER and first is None:
            first = i
        elif first is not None and d[1] == 0x24:
            last = i
        elif first is not None and d[1] == 0x05:
            break
    return first, last


def renumber(items):
    """Recompute AC header wTotalLength and config wTotalLength from the actual bytes."""
    first, last = ac_span(items)
    acl = sum(len(items[i]) for i in range(first, last + 1))
    struct.pack_into("<H", items[first], 6, acl)
    total = sum(len(d) for d in items)
    struct.pack_into("<H", items[0], 2, total)
    return total, acl


# ------------------------------------------------- the patches
def round2_round3(items, copy_no):
    """IAD count, drop the duplicate clock, then the four round-3 byte fixes."""
    log = []
    iad = next(d for d in items if d[1] == 0x0b)
    assert iad[3] == 4
    iad[3] = 3
    log.append("IAD bInterfaceCount 4 -> 3")

    clocks = [i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == CLOCK_SRC]
    assert len(clocks) == 2, "expected 2 clock sources"
    del items[clocks[1]]
    log.append("removed the duplicate CLOCK_SOURCE (-8)")

    clk = next(d for d in items if d[1] == 0x24 and d[2] == CLOCK_SRC)
    assert clk[4] == 0x01
    clk[4] = 0x03
    log.append("clock bmAttributes 0x01 -> 0x03 (internal fixed -> programmable)")

    in_ac = True
    for d in items:
        if d[1] == 0x04:
            in_ac = (d[5], d[6]) == (0x01, 0x01)
        elif d[1] == 0x05 and (d[3] & 0x03) == 0x01 and ((d[3] >> 2) & 0x03) == 0x03:
            if d[2] & 0x80:
                d[3] = 0x05
                log.append("iso IN ep %#02x Synchronous -> Asynchronous" % d[2])
            else:
                d[3] = 0x09
                log.append("iso OUT ep %#02x Synchronous -> Adaptive" % d[2])
        elif d[1] == 0x24 and not in_ac and d[2] == 1:
            nch, cc, names = d[10], struct.unpack("<I", d[11:15])[0], d[15]
            if nch == 2 and bin(cc).count("1") == 1 and names == 0:
                # ROUND 7: 0x03 = FRONT_LEFT | FRONT_RIGHT, the same layout the playback stream
                # declares. Round 3 put 0 here (legal, "no defined spatial location"); Windows and
                # macOS accept it, the iPad registers no input at all.
                struct.pack_into("<I", d, 11, 0x03)
                log.append("record AS_GENERAL bmChannelConfig %#010x -> 0x00000003" % cc)

    if copy_no == 1:
        items[0][8] = 0x06
        log.append("copy B marker: bMaxPower 0x05 -> 0x06")
    return log


def round4(items):
    """Collapse the three mic feature units into one after the selector, and widen both."""
    log = []
    feats = [i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == FEATURE]
    sel_i = next(i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == SELECTOR)
    assert len(feats) == 4, "expected 4 feature units, found %d" % len(feats)
    sel = items[sel_i]
    npins = sel[4]
    pins = list(sel[5:5 + npins])

    # the mic feature units are exactly the ones the selector draws from
    mic_fu = [i for i in feats if items[i][3] in pins]
    play_fu = [i for i in feats if i not in mic_fu]
    assert len(mic_fu) == 3 and len(play_fu) == 1, \
        "expected 3 selector-fed FUs and 1 playback FU, got %d/%d" % (len(mic_fu), len(play_fu))

    # keep the first mic FU's control bitmap and string index for the merged unit
    proto = items[mic_fu[0]]
    merged_id = proto[3]
    master_ctrl = bytes(proto[5:9])
    ifeature = proto[-1]

    # the selector now takes its inputs straight from the mic input terminals
    new_pins = [items[i][4] for i in mic_fu]          # each mic FU's bSourceID = its terminal
    sel[5:5 + npins] = bytes(new_pins)
    log.append("SELECTOR_UNIT %d pins %s -> %s" % (sel[3], pins, new_pins))

    # ROUND 6: the selector's iSelector names string 21, which this device does not have.
    # Measured on hardware: GET_DESCRIPTOR(STRING, 21) returns a STALL, while 17..20 answer
    # ('iAP Interface', 'Internal/External Mic + Instrument', 'External 48V + Instrument').
    # A descriptor field that names a missing string makes the host ask for it and get stalled --
    # which is exactly what the post-round-5 trace showed
    # (GET_DESCRIPTOR type 3 index 0x15 -> USBD_STATUS_STALL_PID, 48 times). 0 = no string.
    # This is a pre-existing defect in Apogee's own descriptor, not something our patches caused;
    # it only became reachable once the descriptor started parsing.
    if sel[-1]:
        log.append("SELECTOR_UNIT %d iSelector %d -> 0 (string %d does not exist on this device)"
                   % (sel[3], sel[-1], sel[-1]))
        sel[-1] = 0

    # the output terminal the selector fed now reads from the merged feature unit
    ot = next(d for d in items if d[1] == 0x24 and d[2] == OUT_TERM and d[7] == sel[3])
    ot[7] = merged_id
    log.append("OUTPUT_TERMINAL %d bSourceID %d -> %d" % (ot[3], sel[3], merged_id))

    # widen the playback feature unit to a 2-channel cluster (its source is the stereo USB
    # stream, so left and right each get the same control bitmap as the master)
    pf = items[play_fu[0]]
    assert len(pf) == 10
    items[play_fu[0]] = bytearray(bytes([18, 0x24, FEATURE, pf[3], pf[4]]) +
                                  bytes(pf[5:9]) * 3 + bytes([pf[9]]))
    log.append("FEATURE_UNIT %d (playback) bLength 10 -> 18, bmaControls master/L/R all %s"
               % (pf[3], bytes(pf[5:9]).hex()))

    # drop the three mic feature units (high index first so the rest stay valid)
    for i in sorted(mic_fu, reverse=True):
        log.append("removed FEATURE_UNIT %d (-%d)" % (items[i][3], len(items[i])))
        del items[i]

    # Insert the merged 2-channel feature unit directly after the selector, and give it
    # PER-CHANNEL control bitmaps: channel 1 is the mic (vendor 0x34), channel 2 the instrument
    # (vendor 0x3E). The master bitmap is kept as well -- a host that only reads the primary
    # control still finds one, and per the Microsoft doc a host that sees both prefers the
    # single-channel ones. This is what the 10-byte original could not express at all.
    sel_i = next(i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == SELECTOR)
    # ROUND 5: advertise NO controls on the mic feature unit. Measured on hardware (USB ETW,
    # 2026-10-02): the firmware ANSWERS Feature Unit 4 volume GET RANGE (status 0x0) but STALLs
    # Feature Unit 10 volume GET RANGE (USBD_STATUS_STALL_PID 0xC0000004), and Windows gives up
    # there. Apogee's own software drove mic gain through vendor request 0x34, so this control was
    # never implemented in firmware. Declaring it is what makes the host ask for it.
    merged = bytearray(bytes([18, 0x24, FEATURE, merged_id, sel[3]]) +
                       bytes(12) + bytes([ifeature]))
    items.insert(sel_i + 1, merged)
    log.append("added FEATURE_UNIT %d after SELECTOR_UNIT %d: bLength 18, bmaControls "
               "master/ch1/ch2 all ZERO (was %s)"
               % (merged_id, sel[3], master_ctrl.hex()))
    return log


def round7(items):
    """Give the three mic input terminals the same stereo layout as their AS_GENERAL."""
    log = []
    in_ac = True
    for d in items:
        if d[1] == 0x04:
            in_ac = (d[5], d[6]) == (0x01, 0x01)
        elif d[1] == 0x24 and in_ac and d[2] == IN_TERM and len(d) == 17:
            cc = struct.unpack("<I", d[9:13])[0]
            if d[8] == 2 and cc == 0:
                struct.pack_into("<I", d, 9, 0x03)
                log.append("INPUT_TERMINAL %d bmChannelConfig 0x00000000 -> 0x00000003" % d[3])
    assert len(log) == 3, "expected 3 mic input terminals with no channel layout, got %d" % len(log)
    return log


# ------------------------------------------------- verification
def ac_entities(items):
    """Only the class-specific descriptors of the AudioControl interface. Scoping matters:
    CS_INTERFACE subtype numbering is context dependent, so an AudioStreaming FORMAT_TYPE
    (subtype 2) would otherwise be mistaken for an AudioControl INPUT_TERMINAL."""
    first, last = ac_span(items)
    return items[first:last + 1]


def channels_of(items, entity_id, depth=0):
    """Trace an entity back to an input terminal to learn its cluster's channel count."""
    assert depth < 16, "topology loop"
    for d in ac_entities(items):
        if d[1] != 0x24:
            continue
        if d[2] == IN_TERM and d[3] == entity_id:
            return d[8]
        if d[2] == FEATURE and d[3] == entity_id:
            return channels_of(items, d[4], depth + 1)
        if d[2] == SELECTOR and d[3] == entity_id:
            chs = {channels_of(items, p, depth + 1) for p in d[5:5 + d[4]]}
            assert len(chs) == 1, "selector %d mixes channel counts %s" % (entity_id, chs)
            return chs.pop()
    raise AssertionError("entity %d not found" % entity_id)


def verify(items, label):
    checks = []
    ids = {}
    acd = ac_entities(items)
    for d in acd:
        if d[1] == 0x24 and d[2] in (IN_TERM, OUT_TERM, MIXER, SELECTOR, FEATURE, CLOCK_SRC):
            checks.append(("entity id %d is unique" % d[3], d[3] not in ids))
            ids[d[3]] = d

    # every feature unit's bLength must match its source cluster
    for d in acd:
        if d[1] == 0x24 and d[2] == FEATURE:
            nch = channels_of(items, d[4])
            want = 6 + (nch + 1) * 4
            checks.append(("FEATURE_UNIT %d bLength %d == 6+(%d+1)*4 = %d"
                           % (d[3], len(d), nch, want), len(d) == want))
    # every bSourceID / selector pin must resolve
    for d in acd:
        if d[1] != 0x24:
            continue
        if d[2] in (OUT_TERM,):
            checks.append(("OUTPUT_TERMINAL %d source %d resolves" % (d[3], d[7]), d[7] in ids))
        if d[2] == FEATURE:
            checks.append(("FEATURE_UNIT %d source %d resolves" % (d[3], d[4]), d[4] in ids))
        if d[2] == SELECTOR:
            for p in d[5:5 + d[4]]:
                checks.append(("SELECTOR_UNIT %d pin %d resolves" % (d[3], p), p in ids))
    # Every string index the descriptor names must actually exist on this device. Measured set:
    # 1,2,3 (manufacturer/product/serial) and 17..20; 4..16 and 21+ all STALL.
    EXISTING = {0, 1, 2, 3, 17, 18, 19, 20}
    for d in items:
        bt = d[1]
        idxs = []
        if bt == 0x02: idxs = [(d[6], "config iConfiguration")]
        elif bt == 0x0b: idxs = [(d[7], "IAD iFunction")]
        elif bt == 0x04: idxs = [(d[8], "interface %d iInterface" % d[2])]
        elif bt == 0x24 and d[2] in (IN_TERM, OUT_TERM, FEATURE, SELECTOR, CLOCK_SRC) and d in acd:
            idxs = [(d[-1], "subtype %#x id %d trailing iString" % (d[2], d[3]))]
            if d[2] == IN_TERM and len(d) == 17:
                idxs.append((d[13], "INPUT_TERMINAL %d iChannelNames" % d[3]))
        for v, what in idxs:
            checks.append(("string index %d (%s) exists" % (v, what), v in EXISTING))

    # ROUND 7: the capture cluster must declare the same stereo layout as playback, and the
    # selector's pins must still all agree -- a Selector Unit may only switch identical clusters.
    as_cc, in_as = [], False
    for d in items:
        if d[1] == 0x04:
            in_as = (d[5], d[6]) == (0x01, 0x02)
        elif d[1] == 0x24 and in_as and d[2] == 1:
            as_cc.append((d[3], d[10], struct.unpack("<I", d[11:15])[0]))
    checks.append(("both AS_GENERAL declare bmChannelConfig 0x3 (%s)" % as_cc,
                   all(cc == 0x03 for _, _, cc in as_cc) and len(as_cc) == 2))
    mic_cc = [(d[3], struct.unpack("<I", d[9:13])[0]) for d in acd
              if d[1] == 0x24 and d[2] == IN_TERM and len(d) == 17 and d[8] == 2
              and (d[4] | (d[5] << 8)) == 0x0201]
    checks.append(("every microphone INPUT_TERMINAL is stereo L/R (%s)" % mic_cc,
                   len(mic_cc) == 3 and all(cc == 0x03 for _, cc in mic_cc)))
    sel = next(d for d in acd if d[1] == 0x24 and d[2] == SELECTOR)
    pin_cc = set()
    for p in sel[5:5 + sel[4]]:
        t = next(x for x in acd if x[1] == 0x24 and x[2] == IN_TERM and x[3] == p)
        pin_cc.add((t[8], struct.unpack("<I", t[9:13])[0]))
    checks.append(("all selector pins carry one identical cluster (%s)" % pin_cc, len(pin_cc) == 1))

    clocks = [d for d in acd if d[1] == 0x24 and d[2] == CLOCK_SRC]
    checks.append(("exactly one clock source", len(clocks) == 1))
    checks.append(("clock bmAttributes == 0x03", clocks[0][4] == 0x03))
    for d in acd:
        if d[1] == 0x24 and d[2] == IN_TERM and len(d) == 17:
            checks.append(("INPUT_TERMINAL %d references clock %d" % (d[3], clocks[0][3]),
                           d[7] == clocks[0][3]))
    iad = next(d for d in items if d[1] == 0x0b)
    checks.append(("IAD bInterfaceCount == 3", iad[3] == 3))
    isos = [d for d in items if d[1] == 0x05 and (d[3] & 0x03) == 0x01]
    checks.append(("no Synchronous iso endpoint", all(((d[3] >> 2) & 3) != 3 for d in isos)))
    first, last = ac_span(items)
    acl = sum(len(items[i]) for i in range(first, last + 1))
    checks.append(("AC wTotalLength == %d" % acl,
                   struct.unpack("<H", items[first][6:8])[0] == acl))
    total = sum(len(d) for d in items)
    checks.append(("config wTotalLength == %d" % total,
                   struct.unpack("<H", items[0][2:4])[0] == total))
    checks.append(("fits the %d-byte slot (%d)" % (SLOT, total), total <= SLOT))

    ok = all(c[1] for c in checks)
    print("    verify %s:" % label)
    bad = [n for n, g in checks if not g]
    for n, g in checks:
        if not g:
            print("       FAIL %s" % n)
    print("       %d checks, %d failed" % (len(checks), len(bad)))
    return ok


# ------------------------------------------------- main
for name in ("ONEv2_USB_Audio_Image0.bin", "ONEv2_USB_Audio_Image1.bin"):
    src = open(os.path.join(FWDIR, name), "rb").read()
    data = bytearray(src)
    cfgs = [i for i in range(len(data)) if data[i:i + len(CFG_SIG)] == CFG_SIG]
    devs = []
    i = data.find(DEV_SIG)
    while i != -1:
        if data[i - 8] == 0x12 and data[i - 7] == 0x01:
            devs.append(i - 8)
        i = data.find(DEV_SIG, i + 1)
    print("=== %s: configs %s, device descriptor %s ==="
          % (name, [hex(c) for c in cfgs], [hex(d) for d in devs]))
    assert len(cfgs) == 2 and len(devs) == 1

    allok = True
    for n, base in enumerate(cfgs):
        items = split(data[base:base + SLOT])
        log = round2_round3(items, n)
        log += round4(items)
        log += round7(items)
        total, acl = renumber(items)
        print("    copy %d @%#07x -> %d bytes (AC class block %d)" % (n, base, total, acl))
        for line in log:
            print("        %s" % line)
        allok &= verify(items, "copy %d" % n)
        blob = join(items)
        assert len(blob) == total <= SLOT
        data[base:base + SLOT] = blob + b"\x00" * (SLOT - len(blob))   # pad the unused tail

    for s in devs:
        assert struct.unpack("<H", data[s + 12:s + 14])[0] == 0x0105
        struct.pack_into("<H", data, s + 12, 0x0110)
        print("    @%#07x bcdDevice 1.05 -> 1.10" % (s + 12))

    dst = os.path.join(OUTDIR, name.replace(".bin", ".R7.patched.bin"))
    open(dst, "wb").write(data)
    diffs = [k for k in range(len(src)) if src[k] != data[k]]
    regions = [(c, c + SLOT) for c in cfgs] + [(s, s + 18) for s in devs]
    stray = [d for d in diffs if not any(lo <= d < hi for lo, hi in regions)]
    print("    bytes changed %d, outside descriptor regions %d %s" % (len(diffs), len(stray), stray[:8]))
    print("    wrote %s -> %s\n" % (dst, "ALL OK" if (allok and not stray) else "*** FAIL ***"))
