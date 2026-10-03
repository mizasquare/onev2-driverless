#!/usr/bin/env python3
"""Decode a USBXHCI ETW capture into "which UAC2 class control requests crossed the wire, in what
order, and what the device answered".

Usage:  parse-classreq.py <tracerpt-xml> [phases.json]

Reading the output:
  status 0x00000000  the device answered the request
  status 0xC0000004  USBD_STATUS_STALL_PID -- the device STALLed it
Anything else is printed raw; those are usually transport-level, not the device's verdict.

Our device is identified by its own vendor traffic (bmRequestType 0x40/0xC0), which the exerciser
generates continuously, so no guessing from descriptor sizes is needed. Hub port management is also
class-typed but recipient=OTHER, so the recipient field keeps it out of the way.
"""
import re, sys, json, collections

sys.stdout.reconfigure(encoding="utf-8")

XML = sys.argv[1]
PHASES = sys.argv[2] if len(sys.argv) > 2 else None

FIELDS = ("fid_URB_Setup_bmRequestType", "fid_URB_Setup_bRequest", "fid_URB_Setup_wValue",
          "fid_URB_Setup_wIndex", "fid_URB_Setup_wLength", "fid_URB_Hdr_Status",
          "fid_URB_Hdr_UsbdDeviceHandle", "fid_URB_Hdr_Function", "fid_URB_Ptr")
pats = {k: re.compile(r'<Data Name="%s">([^<]*)</Data>' % k) for k in FIELDS}
tpat = re.compile(r'SystemTime="([^"]+)"')

TYPE = {0: "std", 1: "class", 2: "vendor", 3: "rsvd"}
RECIP = {0: "device", 1: "iface", 2: "endpoint", 3: "other"}
ATTR = {0x01: "CUR", 0x02: "RANGE", 0x03: "MEM"}
STATUS = {0x00000000: "OK", 0xC0000004: "STALL", 0x40000000: "PENDING",
          0xC0000030: "ENDPOINT_HALTED", 0xC0007000: "CANCELED"}
STD = {0x00: "GET_STATUS", 0x01: "CLEAR_FEATURE", 0x03: "SET_FEATURE", 0x05: "SET_ADDRESS",
       0x06: "GET_DESCRIPTOR", 0x08: "GET_CONFIGURATION", 0x09: "SET_CONFIGURATION",
       0x0A: "GET_INTERFACE", 0x0B: "SET_INTERFACE"}
# control selectors, by the kind of entity the id belongs to in the live R6 descriptor
ENTITY = {1: "CLOCK_SOURCE", 4: "FEATURE_UNIT(play)", 10: "FEATURE_UNIT(cap)",
          15: "SELECTOR_UNIT", 2: "IT(usb)", 3: "OT(play)", 8: "OT(usb)",
          9: "IT(int mic)", 11: "IT(ext)", 13: "IT(ext48)"}
CS_CLOCK = {0x01: "SAM_FREQ", 0x02: "CLOCK_VALID"}
CS_FU = {0x01: "MUTE", 0x02: "VOLUME", 0x03: "BASS", 0x04: "MID", 0x05: "TREBLE",
         0x07: "AGC", 0x08: "DELAY", 0x0A: "LOUDNESS"}
CS_SU = {0x01: "SELECTOR"}
CS_AS = {0x01: "AS_ACT_ALT_SETTING", 0x02: "AS_VAL_ALT_SETTINGS", 0x03: "AS_AUDIO_DATA_FORMAT"}


def h(x):
    if not x:
        return 0
    try:
        return int(x, 16) if str(x).lower().startswith("0x") else int(x)
    except Exception:
        return 0


def cs_name(entity, cs):
    if entity == 0:
        return CS_AS.get(cs, "CS%#04x" % cs)
    e = ENTITY.get(entity, "")
    if e.startswith("CLOCK"):
        return CS_CLOCK.get(cs, "CS%#04x" % cs)
    if e.startswith("FEATURE"):
        return CS_FU.get(cs, "CS%#04x" % cs)
    if e.startswith("SELECTOR"):
        return CS_SU.get(cs, "CS%#04x" % cs)
    return "CS%#04x" % cs


def stat(s):
    v = h(s)
    return "%s(%#010x)" % (STATUS.get(v, "?"), v) if s is not None else "-"


rows, buf, CH = [], "", 1 << 22
with open(XML, "r", encoding="utf-8", errors="replace") as f:
    while True:
        chunk = f.read(CH)
        if not chunk:
            break
        buf += chunk
        while True:
            i = buf.find("</Event>")
            if i < 0:
                break
            blk, buf = buf[:i], buf[i + 8:]
            # the start tag is "<Event>" or "<Event ...>" -- NOT "<EventData>", which a plain
            # rfind("<Event") would latch onto, silently throwing away the <System> block and with
            # it every timestamp.
            j = max(blk.rfind("<Event>"), blk.rfind("<Event "))
            if j < 0:
                continue
            blk = blk[j:]
            if not pats["fid_URB_Setup_bmRequestType"].search(blk):
                continue
            g = {}
            for k in FIELDS:
                m = pats[k].search(blk)
                g[k] = m.group(1) if m else None
            tm = tpat.search(blk)
            rows.append({
                "t": (tm.group(1)[11:23] if tm else "?"),
                "brt": h(g["fid_URB_Setup_bmRequestType"]), "req": h(g["fid_URB_Setup_bRequest"]),
                "val": h(g["fid_URB_Setup_wValue"]), "idx": h(g["fid_URB_Setup_wIndex"]),
                "len": h(g["fid_URB_Setup_wLength"]), "st": g["fid_URB_Hdr_Status"],
                "dev": g["fid_URB_Hdr_UsbdDeviceHandle"], "urb": g["fid_URB_Ptr"],
            })

# UCX logs each control transfer twice: a dispatch (status 0x40000000 PENDING) and a completion
# carrying the real verdict. Pair them by URB pointer -- matching the dispatch with the NEXT
# completion for that pointer, since pointers are recycled -- so one request is reported once with
# the status that matters.
paired, pending = [], {}
for r in rows:
    if h(r["st"]) == 0x40000000:
        pending[r["urb"]] = r
        paired.append(r)
    elif r["urb"] in pending:
        d = pending.pop(r["urb"])
        d["st"] = r["st"]
    else:
        paired.append(r)
unfinished = sum(1 for r in paired if h(r["st"]) == 0x40000000)
rows = paired

print("setup packets in the capture: %d (%d never completed inside the window)"
      % (len(rows), unfinished))
by = collections.Counter((TYPE[(r["brt"] >> 5) & 3], RECIP.get(r["brt"] & 0x1F, "?")) for r in rows)
print("by (type, recipient): %s" % dict(by))

ours = set(r["dev"] for r in rows
           if ((r["brt"] >> 5) & 3) == 2 and r["req"] in (0x28, 0x34, 0x36))
if ours:
    print("our device handle(s), by Apogee 0x28/0x34/0x36 traffic: %s" % sorted(ours))
else:
    anyvendor = collections.Counter(r["dev"] for r in rows if ((r["brt"] >> 5) & 3) == 2)
    if anyvendor:
        ours = set(anyvendor)
        print("no 0x28/0x34/0x36 seen; falling back to every handle with vendor traffic: %s"
              % dict(anyvendor))
        print("  (if more than one handle is listed, another device is also using vendor requests)")
    else:
        print("our device handle(s): NONE")
        print("\nNo vendor requests at all in this capture. Either the exerciser did not run inside")
        print("the window, or the provider/keywords did not record EP0 -- the URB_Setup fields come")
        print("from Microsoft-Windows-USB-UCX, not from USBXHCI. Nothing below can be trusted.")
mine = [r for r in rows if r["dev"] in ours] if ours else rows

phases = None
if PHASES:
    try:
        with open(PHASES, encoding="utf-8") as f:
            phases = json.load(f)["phases"]
    except Exception as e:
        print("(could not read the phase log: %s)" % e)

print("\n=== every CLASS request to our device, in time order ===")
cls = [r for r in mine if ((r["brt"] >> 5) & 3) == 1 and (r["brt"] & 0x1F) in (1, 2)]
if not cls:
    print("  NONE. usbaudio2 issued no class requests in this window.")
pi = 0
for r in cls:
    while (phases and pi < len(phases) and r["t"] != "?"
           and phases[pi]["start"] <= r["t"]):
        p = phases[pi]
        print("  -- P%-2d %s  (selector %d->%d) %s"
              % (p["n"], p["what"], p["sel_before"], p["sel_after"], p["note"]))
        pi += 1
    ent, iface = r["idx"] >> 8, r["idx"] & 0xFF
    cs, cn = r["val"] >> 8, r["val"] & 0xFF
    print("   %s %-3s %-5s %-18s %-12s ch%-2d iface=%d wLen=%-3d %s"
          % (r["t"], "IN" if r["brt"] & 0x80 else "OUT", ATTR.get(r["req"], "%#04x" % r["req"]),
             "%s %d" % (ENTITY.get(ent, "entity"), ent), cs_name(ent, cs), cn, iface,
             r["len"], stat(r["st"])))

print("\n=== class requests aggregated ===")
agg = collections.Counter()
for r in cls:
    ent = r["idx"] >> 8
    agg[(("IN" if r["brt"] & 0x80 else "OUT"), ATTR.get(r["req"], hex(r["req"])), ent,
         cs_name(ent, r["val"] >> 8), r["val"] & 0xFF, r["idx"] & 0xFF, stat(r["st"]))] += 1
for (d, a, ent, cs, cn, iface, st), n in sorted(agg.items(), key=lambda kv: -kv[1]):
    print("  x%-4d %-3s %-5s %-18s %-12s ch%-2d iface=%d  %s"
          % (n, d, a, "%s %d" % (ENTITY.get(ent, "entity"), ent), cs, cn, iface, st))

print("\n=== SET_INTERFACE / GET_DESCRIPTOR on our device (brackets the stream starts) ===")
for r in mine:
    if ((r["brt"] >> 5) & 3) == 0 and r["req"] in (0x0B, 0x06):
        print("   %s %-15s wValue=%#06x wIndex=%#06x wLen=%-4d %s"
              % (r["t"], STD.get(r["req"], hex(r["req"])), r["val"], r["idx"], r["len"],
                 stat(r["st"])))

print("\n=== vendor requests aggregated (ours, for reference) ===")
ven = collections.Counter((("IN" if r["brt"] & 0x80 else "OUT"), r["req"], stat(r["st"]))
                          for r in mine if ((r["brt"] >> 5) & 3) == 2)
for (d, req, st), n in sorted(ven.items(), key=lambda kv: -kv[1])[:12]:
    print("  x%-4d %-3s bRequest=%#04x  %s" % (n, d, req, st))

stalls = [r for r in cls if h(r["st"]) == 0xC0000004]
oks = [r for r in cls if h(r["st"]) == 0]
print("\nVERDICT: %d class requests, %d answered, %d STALLed." % (len(cls), len(oks), len(stalls)))
if cls and not stalls:
    print("  Every class request the host sent was answered -> the firmware's UAC2 control")
    print("  handler covers everything usbaudio2 actually asks for.")
elif stalls:
    print("  The STALLed ones are what a stricter host (iPadOS) could trip over:")
    for (d, a, ent, cs, cn, iface, st), n in sorted(agg.items()):
        if "STALL" in st:
            print("    x%-3d %s %s %s %s ch%d iface=%d" % (n, d, a, ENTITY.get(ent, ent), cs, cn, iface))
