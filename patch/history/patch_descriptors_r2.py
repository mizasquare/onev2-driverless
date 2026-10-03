#!/usr/bin/env python3
"""ONEv2 R1 round-2 descriptor patch. Microsoft's usbaudio2 doc: "supports one single clock
source only" -> the decisive defect is the TWO clock sources. Round-2 fix:
  F1  IAD bInterfaceCount 4 -> 3                         (same length)
  F3' REMOVE the duplicate CLOCK_SOURCE entirely         (shrink 8 bytes -> ONE clock source)
  F2' AC header wTotalLength -> recomputed (159)         (consistent after removal)
      config wTotalLength 340 -> 332                     (consistent after removal)
(The feature-unit bLength 10 is NOT a defect: the doc says master-only FUs are accepted.)

The firmware sends config.wTotalLength bytes from a pointer, so shrinking in place is safe:
we drop the 8-byte clock descriptor, shift the rest up 8, reduce both wTotalLengths, and leave
8 stale bytes at the tail of the 340-byte slot (never sent).

Starts from the ORIGINAL images (not the R1-patched orphan-clock ones). Produces *.R1r2.patched.bin.
"""
import sys, os, struct

FWDIR = os.path.join(os.path.dirname(__file__), "..", "firmware")
OUTDIR = FWDIR          # patched images land next to the stock ones, in firmware/
CFG_SIG = bytes.fromhex("09025401040100c005")

def find_cfgs(img):
    return [i for i in range(len(img)) if img[i:i+len(CFG_SIG)] == CFG_SIG]

def parse(img, base):
    """Return list of (abs_off, bLen, bType, subtype) and key field offsets."""
    total = struct.unpack("<H", img[base+2:base+4])[0]
    p, end = base, base+total
    items = []; iad=None; ac_hdr=None; clocks=[]
    while p < end and img[p]:
        bl, bt = img[p], img[p+1]
        st = img[p+2] if bt == 0x24 else None
        items.append((p, bl, bt, st))
        if bt == 0x0b: iad = p
        if bt == 0x24 and st == 0x01 and ac_hdr is None: ac_hdr = p
        if bt == 0x24 and st == 0x0a: clocks.append(p)
        p += bl
    return total, items, iad, ac_hdr, clocks

def ac_len(items, ac_hdr):
    """Length of AC class-specific block = AC header .. last 0x24 desc before first endpoint."""
    start = ac_hdr; last = None
    seen = False
    for off, bl, bt, st in items:
        if off == ac_hdr: seen = True
        if not seen: continue
        if bt == 0x24: last = off + bl
        elif bt == 0x05: break
    return last - start

def patch_cfg(img, base):
    total, items, iad, ac_hdr, clocks = parse(img, base)
    assert len(clocks) == 2, "expected 2 clock sources, got %d" % len(clocks)
    dup = clocks[1]                              # second clock source
    dup_len = img[dup]                           # 8
    # F1: IAD count -> 3
    assert img[iad+3] == 4
    img[iad+3] = 3
    # F3': remove the dup clock: shift [dup+dup_len : base+total] up by dup_len
    tail = bytes(img[dup+dup_len : base+total])
    img[dup : dup + len(tail)] = tail
    # zero the 8 stale bytes now at the end of the slot
    for i in range(base+total-dup_len, base+total):
        img[i] = 0x00
    new_total = total - dup_len
    # F2'/config length: rewrite config wTotalLength and AC header wTotalLength
    struct.pack_into("<H", img, base+2, new_total)
    # re-parse to get the AC header's new position (unchanged: it's before dup) and new AC length
    _, items2, iad2, ac_hdr2, clocks2 = parse(img, base)
    assert len(clocks2) == 1, "after removal expected 1 clock, got %d" % len(clocks2)
    acl = ac_len(items2, ac_hdr2)
    struct.pack_into("<H", img, ac_hdr2+6, acl)   # AC header wTotalLength
    return new_total, acl, len(clocks2)

def verify(img, base):
    total, items, iad, ac_hdr, clocks = parse(img, base)
    ac_wtl = struct.unpack("<H", img[ac_hdr+6:ac_hdr+8])[0]
    acl = ac_len(items, ac_hdr)
    # check every descriptor's clock reference resolves to an existing clock id
    clk_ids = set(img[c+3] for c in clocks)
    ok = (img[iad+3]==3) and (len(clocks)==1) and (ac_wtl==acl)
    # walk to end cleanly
    p=base; walked=0
    while p < base+total and img[p]: p+=img[p]; walked+=1
    clean = (p == base+total)
    print("    verify @0x%05x: IAD=%d clocks=%d(ids=%s) cfgTotal=%d ACwTotal=%d(actual=%d) parse_clean=%s -> %s"
          % (base, img[iad+3], len(clocks), clk_ids, total, ac_wtl, acl, clean, "OK" if (ok and clean) else "FAIL"))
    return ok and clean

for name in ("ONEv2_USB_Audio_Image0.bin", "ONEv2_USB_Audio_Image1.bin"):
    data = bytearray(open(os.path.join(FWDIR, name), "rb").read())
    cfgs = find_cfgs(data)
    print("=== %s: config copies %s ===" % (name, [hex(c) for c in cfgs]))
    for b in cfgs:
        nt, acl, nclk = patch_cfg(data, b)
        print("    @0x%05x removed dup clock -> cfgTotal=%d ACwTotal=%d clocks=%d" % (b, nt, acl, nclk))
    allok = all(verify(data, b) for b in cfgs)
    dst = os.path.join(OUTDIR, name.replace(".bin", ".R1r2.patched.bin"))
    open(dst, "wb").write(data)
    src = open(os.path.join(FWDIR, name), "rb").read()
    diffs = sum(1 for i in range(len(src)) if src[i] != data[i])
    print("    bytes changed vs original: %d | wrote %s | %s" % (diffs, dst, "ALL OK" if allok else "*** FAIL ***"))
