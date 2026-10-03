#!/usr/bin/env python3
"""ONEv2 descriptor patch, round 3. Starts from the ORIGINAL images and applies everything,
so this one script fully defines the firmware (no patch chaining). Output: *.R3.patched.bin

Carried over from round 2 (structural):
  S1  IAD bInterfaceCount 4 -> 3                  (vendor IF3 out of the audio function)
  S2  remove the duplicate CLOCK_SOURCE           (-8 bytes; MS: "one single clock source only")
  S3  recompute config wTotalLength 340 -> 332 and AC header wTotalLength -> 159

New in round 3 -- four 1-byte fixes, each a self-contradiction verified in the LIVE 332-byte
descriptor read back off the device:
  F1  CLOCK_SOURCE bmAttributes 0x01 -> 0x03
        0x01 = internal FIXED, but bmControls 0x07 advertises a host-settable frequency control.
        0x03 = internal PROGRAMMABLE. SOF-sync bit (D2) stays clear, same as the known-good
        TinyUSB uac2_headset reference.
  F2  iso OUT endpoint bmAttributes 0x0d -> 0x09   Synchronous -> Adaptive
  F3  iso IN  endpoint bmAttributes 0x0d -> 0x05   Synchronous -> Asynchronous
        Synchronous means SOF-locked, which contradicts a non-SOF internal clock. Known-good
        uses Adaptive OUT / Async IN with exactly this clock type. Async IN needs no feedback
        endpoint (explicit feedback is mandatory only for Async OUT), so nothing is added.
  F4  record AS_GENERAL bmChannelConfig 0x00000004 -> 0x00000000
        It declared bNrChannels=2 with ONE spatial bit (Front Center) and iChannelNames=0:
        1 located + 0 named != 2. Its own upstream terminals all declare 0x00000000.

Diagnostics (do not affect compliance):
  D1  bcdDevice 0x0105 -> 0x0106
        So the host can tell at a glance which firmware is live, and so Windows re-evaluates the
        device under a fresh UsbFlags key instead of reusing the old one.
  D2  bMaxPower: copy A keeps 0x05, copy B becomes 0x06
        The two config copies are byte-identical, 340 bytes apart, back to back -- almost
        certainly ASF's full-speed and high-speed configuration descriptors. We do not know
        which one a high-speed host is served. This marker byte makes the live dump say so,
        which decides whether the Feature Unit fix (needs +32 bytes, would overrun into copy B)
        can be done in place at all.

NOT fixed here, deliberately: FEATURE_UNIT bLength 10 on all four units. Per ADC-2 4.7.2.8
bLength = 6 + (nch+1)*4, so a 2-channel cluster requires 18, and every source terminal declares
bNrChannels=2 -- a hard, formula-level violation and the strongest remaining candidate. It needs
+32 bytes (332 -> 364) and the slot only has 8 spare, so it is round 3b, gated on D2's answer.
"""
import os, struct

FWDIR = os.path.join(os.path.dirname(__file__), "..", "firmware")
OUTDIR = FWDIR          # patched images land next to the stock ones, in firmware/
CFG_SIG = bytes.fromhex("09025401040100c005")        # original 340-byte config header
DEV_SIG = bytes.fromhex("600c17000501")              # idVendor/idProduct/bcdDevice


# ------------------------------------------------------------------ parsing
def walk(img, base):
    """Yield (offset, bLength, bDescriptorType, subtype) for one config descriptor."""
    total = struct.unpack("<H", img[base+2:base+4])[0]
    p, end = base, base + total
    while p < end and img[p]:
        bl, bt = img[p], img[p+1]
        st = img[p+2] if bt in (0x24, 0x25) else None
        yield p, bl, bt, st
        p += bl


def index(img, base):
    """Locate the entities we patch, by parsing -- never by hardcoded offsets.
    Note: CS_INTERFACE subtype numbering is context dependent. Inside the AudioControl
    interface, subtype 1 = AC_HEADER and 2 = INPUT_TERMINAL; inside an AudioStreaming
    interface, subtype 1 = AS_GENERAL and 2 = FORMAT_TYPE. Track which interface we are in."""
    r = {"iad": None, "ac_hdr": None, "clocks": [], "in_terms": [], "feats": [],
         "as_general": [], "eps": [], "cur_if": None}
    in_ac = False
    for off, bl, bt, st in walk(img, base):
        if bt == 0x0b:
            r["iad"] = off
        elif bt == 0x04:
            r["cur_if"] = off
            in_ac = (img[off+5], img[off+6]) == (0x01, 0x01)   # AUDIO / AUDIOCONTROL
        elif bt == 0x24 and in_ac:
            if st == 0x01 and r["ac_hdr"] is None: r["ac_hdr"] = off
            elif st == 0x02: r["in_terms"].append(off)
            elif st == 0x06: r["feats"].append(off)
            elif st == 0x0a: r["clocks"].append(off)
        elif bt == 0x24 and not in_ac:
            if st == 0x01: r["as_general"].append(off)
        elif bt == 0x05:
            r["eps"].append(off)
    return r


def ac_class_len(img, base):
    """AC header .. last class-specific AC descriptor, i.e. the AC header's wTotalLength."""
    idx = index(img, base)
    start, last = idx["ac_hdr"], None
    seen = False
    for off, bl, bt, st in walk(img, base):
        if off == start: seen = True
        if not seen: continue
        if bt == 0x24: last = off + bl
        elif bt == 0x05: break
    return last - start


# ------------------------------------------------------------------ patches
def structural(img, base):
    """Round-2 work: IAD count, drop the duplicate clock, fix both wTotalLengths."""
    total = struct.unpack("<H", img[base+2:base+4])[0]
    idx = index(img, base)
    assert len(idx["clocks"]) == 2, "expected 2 clock sources, got %d" % len(idx["clocks"])
    assert img[idx["iad"]+3] == 4, "IAD bInterfaceCount is %d, expected 4" % img[idx["iad"]+3]
    img[idx["iad"]+3] = 3
    dup = idx["clocks"][1]
    dlen = img[dup]
    tail = bytes(img[dup+dlen: base+total])
    img[dup: dup+len(tail)] = tail
    for i in range(base+total-dlen, base+total):
        img[i] = 0x00                                  # stale bytes, never sent
    struct.pack_into("<H", img, base+2, total - dlen)
    struct.pack_into("<H", img, index(img, base)["ac_hdr"]+6, ac_class_len(img, base))
    return total - dlen


def byte_fixes(img, base, copy_no):
    """The four compliance bytes plus the copy marker. Returns a list of (off, old, new, why)."""
    idx = index(img, base)
    done = []

    def setb(off, new, why):
        old = img[off]
        if old != new:
            img[off] = new
            done.append((off, old, new, why))

    # F1 clock bmAttributes (CLOCK_SOURCE +4)
    clk = idx["clocks"][0]
    assert img[clk+4] == 0x01, "clock bmAttributes is %#02x, expected 0x01" % img[clk+4]
    setb(clk+4, 0x03, "F1 clock bmAttributes internal-fixed -> internal-programmable")

    # F2/F3 the two isochronous data endpoints (bmAttributes +3, transfer type bits 1:0 == 01b)
    iso = [o for o in idx["eps"] if (img[o+3] & 0x03) == 0x01 and ((img[o+3] >> 2) & 0x03) == 0x03]
    assert len(iso) == 2, "expected 2 synchronous iso endpoints, found %d" % len(iso)
    for o in iso:
        if img[o+2] & 0x80:
            setb(o+3, 0x05, "F3 iso IN  ep %#02x Synchronous -> Asynchronous" % img[o+2])
        else:
            setb(o+3, 0x09, "F2 iso OUT ep %#02x Synchronous -> Adaptive" % img[o+2])

    # F4 the record AS_GENERAL: the one whose bTerminalLink is an OUTPUT terminal fed by the
    # selector. Identify it as the AS_GENERAL whose bmChannelConfig has exactly one bit set
    # while bNrChannels is 2 -- that is the contradiction we are fixing.
    for o in idx["as_general"]:
        nch = img[o+10]
        cc = struct.unpack("<I", img[o+11:o+15])[0]
        names = img[o+15]
        if nch == 2 and bin(cc).count("1") == 1 and names == 0:
            struct.pack_into("<I", img, o+11, 0)
            done.append((o+11, cc, 0, "F4 AS_GENERAL bmChannelConfig %#010x -> 0 (2ch, 1 bit, 0 names)" % cc))

    # D2 copy marker in bMaxPower (config byte 8)
    if copy_no == 1:
        setb(base+8, 0x06, "D2 copy B marker: bMaxPower 0x05 -> 0x06")
    return done


def find_device_descriptors(img):
    """Offsets of the 18-byte DEVICE descriptors. Call BEFORE patching: the search key includes
    bcdDevice, which the patch changes."""
    out, i = [], img.find(DEV_SIG)
    while i != -1:
        s = i - 8
        if img[s] == 0x12 and img[s+1] == 0x01:
            out.append(s)
        i = img.find(DEV_SIG, i + 1)
    return out


def patch_device_descriptor(img, devs):
    """D1 bcdDevice 1.05 -> 1.06, so the live firmware revision is visible from the host."""
    out = []
    for s in devs:
        assert struct.unpack("<H", img[s+12:s+14])[0] == 0x0105
        struct.pack_into("<H", img, s+12, 0x0106)
        out.append((s+12, 0x0105, 0x0106, "D1 bcdDevice 1.05 -> 1.06"))
    return out


# ------------------------------------------------------------------ verify
def verify(img, base, label):
    total = struct.unpack("<H", img[base+2:base+4])[0]
    idx = index(img, base)
    checks = []
    checks.append(("IAD bInterfaceCount == 3", img[idx["iad"]+3] == 3))
    checks.append(("exactly 1 clock source", len(idx["clocks"]) == 1))
    clk = idx["clocks"][0]
    checks.append(("clock bmAttributes == 0x03", img[clk+4] == 0x03))
    clk_id = img[clk+3]
    refs = [img[o+7] for o in idx["in_terms"]]
    checks.append(("all input terminals reference clock %d" % clk_id, all(r == clk_id for r in refs)))
    acl = ac_class_len(img, base)
    checks.append(("AC wTotalLength consistent (%d)" % acl,
                   struct.unpack("<H", img[idx["ac_hdr"]+6:idx["ac_hdr"]+8])[0] == acl))
    iso = [o for o in idx["eps"] if (img[o+3] & 0x03) == 0x01]
    syncs = [((img[o+3] >> 2) & 0x03) for o in iso]
    checks.append(("no Synchronous iso endpoint left", 3 not in syncs))
    bad_cc = []
    for o in idx["as_general"]:
        nch, cc, names = img[o+10], struct.unpack("<I", img[o+11:o+15])[0], img[o+15]
        if cc and bin(cc).count("1") + names < nch:
            bad_cc.append((o, nch, cc, names))
    checks.append(("every AS_GENERAL channel cluster adds up", not bad_cc))
    # the descriptor must still walk exactly to wTotalLength
    p = base
    while p < base + total and img[p]:
        p += img[p]
    checks.append(("walks cleanly to wTotalLength (%d)" % total, p == base + total))
    # and must not have grown past its 340-byte slot
    checks.append(("fits the 340-byte slot", total <= 340))
    ok = all(c[1] for c in checks)
    print("    verify %s:" % label)
    for name, good in checks:
        print("       %s %s" % ("OK  " if good else "FAIL", name))
    return ok


# ------------------------------------------------------------------ main
for name in ("ONEv2_USB_Audio_Image0.bin", "ONEv2_USB_Audio_Image1.bin"):
    src_path = os.path.join(FWDIR, name)
    src = open(src_path, "rb").read()
    data = bytearray(src)
    cfgs = [i for i in range(len(data)) if data[i:i+len(CFG_SIG)] == CFG_SIG]
    devs = find_device_descriptors(data)
    print("=== %s: config copies at %s, device descriptor(s) at %s ==="
          % (name, [hex(c) for c in cfgs], [hex(x) for x in devs]))
    assert len(cfgs) == 2, "expected 2 config copies, found %d" % len(cfgs)
    assert len(devs) == 1, "expected 1 device descriptor, found %d" % len(devs)

    for n, b in enumerate(cfgs):
        new_total = structural(data, b)
        print("    @%#07x structural -> wTotalLength %d" % (b, new_total))
        for off, old, new, why in byte_fixes(data, b, n):
            print("    @%#07x  %#x -> %#x   %s" % (off, old, new, why))
    for off, old, new, why in patch_device_descriptor(data, devs):
        print("    @%#07x  %#x -> %#x   %s" % (off, old, new, why))

    allok = all(verify(data, b, "copy %d @%#07x" % (n, b)) for n, b in enumerate(cfgs))
    dst = os.path.join(OUTDIR, name.replace(".bin", ".R3.patched.bin"))
    open(dst, "wb").write(data)
    diffs = [i for i in range(len(src)) if src[i] != data[i]]
    # every changed byte must live in a config copy or the device descriptor
    regions = [(c, c+340) for c in cfgs] + [(s, s+18) for s in devs]
    stray = [d for d in diffs if not any(lo <= d < hi for lo, hi in regions)]
    print("    bytes changed: %d | outside the descriptor regions: %d %s"
          % (len(diffs), len(stray), [hex(s) for s in stray[:8]]))
    print("    wrote %s  ->  %s\n" % (dst, "ALL OK" if (allok and not stray) else "*** FAIL ***"))
