#!/usr/bin/env python3
"""Provoke, on purpose and in a known order, every UAC2 class control request we want to see on
the wire. Meant to be run INSIDE an active USBXHCI ETW capture (see capture-classreq2.bat).

Why each phase exists:
  - the clock phases make the host retune the device, which under UAC2 is only possible with
    SET CUR / GET RANGE on CS_SAM_FREQ_CONTROL;
  - the capture phases make it switch source, which is only possible with SET CUR on
    SELECTOR_UNIT 15;
  - the last capture phase is the open question: starting from a NON-zero selector value the host
    appeared not to issue the SET at all. On the wire we will see whether it never sends it, or
    sends it and the device STALLs it.

Two independent ways to line the trace up with these phases:
  1. a sidecar JSON of UTC timestamps per phase, written next to the ETL -- the primary mechanism,
     since ETW stamps events with the same system clock;
  2. a burst of N vendor 0x28 reads (firmware version, 3 bytes, pure getter) before phase N, which
     show up in the trace as vendor requests and need no clock agreement at all.

Robustness notes, both learned the hard way on this device:
  - 0x28 is a THREE byte read. Asking for 4 returns an I/O error AND kills the WinUSB handle, and
    the device then re-enumerates, which invalidates every PortAudio device index in the process.
  - so device indices are resolved immediately before use, and a failed open re-initialises
    PortAudio once and retries. Nothing here hardcodes an index.

Everything is a GET except the vendor 0x36 writes that move the input selector. The device is left
on Internal Mic with phantom power off.
"""
import sys, os, time, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import sounddevice as sd
import onev2_flash as F

OUT = os.environ.get("CLASSREQ_PHASES", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "usbtrace-classreq-phases.json"))
NAMES = {0: "Internal Mic", 1: "External", 2: "External +48V"}
SECS = 0.5
RATES = (44100, 48000, 96000)

one = F.open_one(3)
phases = []
markers_ok = True


def vr(req, n):
    for _ in range(12):
        try:
            return one.rd(req, 0, 0, n)
        except Exception:
            one.reconnect()
    raise IOError("vendor read %#x" % req)


def vw(req, v):
    for _ in range(12):
        try:
            one.wr(req, 0, 0, bytes([v]))
            return
        except Exception:
            one.reconnect()
    raise IOError("vendor write %#x" % req)


def sel():
    return vr(0x36, 1)[0]


def now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def mark(n):
    """n consecutive vendor 0x28 reads = 'phase n starts here'. Never retries: a marker is a
    convenience, and a retry storm here is what broke the first version of this script."""
    global markers_ok
    time.sleep(0.4)
    if markers_ok:
        for _ in range(n):
            try:
                one.rd(0x28, 0, 0, 3)
            except Exception:
                markers_ok = False
                print("     (markers disabled: 0x28 read failed; timestamps still align)")
                break
            time.sleep(0.05)
    time.sleep(0.4)


def ports(reinit=False):
    """Current PortAudio view. Re-initialising re-enumerates after the device has dropped off and
    come back, but it also churns the index space and has produced spurious 'Invalid device' on
    this machine, so only do it once an open has already failed."""
    if reinit:
        try:
            sd._terminate(); sd._initialize()
        except Exception:
            pass
    outs, ins = [], []
    for i, d in enumerate(sd.query_devices()):
        if "ONEv2" not in d["name"]:
            continue
        if sd.query_hostapis(d["hostapi"])["name"] != "Windows WASAPI":
            continue
        (outs if d["max_output_channels"] > 0 else ins).append((i, d["default_samplerate"]))
    return outs, ins


def run_stream(kind, which, sr, exclusive):
    """Open one stream, re-resolving and escalating the recovery if an attempt fails."""
    last = None
    for attempt in (0, 1, 2):
        if attempt:
            time.sleep(1.0 * attempt)
        outs, ins = ports(reinit=bool(attempt))
        pool = outs if kind == "out" else ins
        if which >= len(pool):
            return "no such %s endpoint any more (%d available)" % (kind, len(pool))
        dev, dflt = pool[which]
        rate = sr or int(dflt)
        xs = sd.WasapiSettings(exclusive=True) if exclusive else None
        try:
            if kind == "out":
                with sd.OutputStream(device=dev, samplerate=rate, channels=2, dtype="float32",
                                     extra_settings=xs) as st:
                    st.write(np.zeros((int(rate * SECS), 2), dtype="float32"))
            else:
                with sd.InputStream(device=dev, samplerate=rate, channels=2, dtype="float32",
                                    extra_settings=xs) as st:
                    st.read(int(rate * SECS))
            return "%s %s dev %d @ %d Hz" % ("exclusive" if exclusive else "shared",
                                             kind, dev, rate)
        except Exception as e:
            last = str(e).splitlines()[0][:70]
    return "FAILED: %s" % last


def phase(n, what, fn):
    mark(n)
    t0 = now()
    before = sel()
    try:
        note = fn() or ""
    except Exception as e:
        note = "FAILED: %s" % str(e).splitlines()[0][:70]
    after = sel()
    t1 = now()
    phases.append({"n": n, "what": what, "start": t0, "end": t1,
                   "sel_before": before, "sel_after": after, "note": note})
    print("  P%-2d %-46s %s..%s  sel %d->%d  %s" % (n, what, t0, t1, before, after, note))
    return after


def from_zero(which):
    def go():
        vw(0x36, 0)
        time.sleep(0.4)
        return run_stream("in", which, None, False)
    return go


outs, ins = ports()
print("firmware version 0x28 = %s   keep-alive 0x29 = %s"
      % (vr(0x28, 3).hex(), vr(0x29, 6).hex()))
print("WASAPI endpoints: %d output, %d capture" % (len(outs), len(ins)))
print("start %s UTC\n" % now())

def soft_reset():
    """Vendor 0xA7. Forces a full re-enumeration inside the capture window, which is the only way
    to see the requests Windows asks once at bind time and then caches -- GET_DESCRIPTOR, the
    clock's GET RANGE and CLOCK_VALID. Those are exactly what iPadOS will ask on connect."""
    try:
        one.wr(0xA7, 0, 0, b"\x00")
    except Exception:
        pass                                  # the device goes away mid-request; that is the point
    time.sleep(2.0)
    if not one.reconnect(tries=80, delay=0.4):
        return "FAILED: device did not come back after the soft reset"
    time.sleep(3.0)                           # let usbaudio2 finish binding and asking
    return "soft reset, device re-enumerated"


n = 1
if "--reset" in sys.argv:
    phase(0, "soft reset to force a fresh enumeration", soft_reset)
phase(n, "idle, no stream", lambda: (time.sleep(2.0), "baseline")[1]); n += 1
for sr in RATES:
    phase(n, "output exclusive %d" % sr,
          (lambda s: (lambda: run_stream("out", 0, s, True)))(sr)); n += 1

# self-calibrating: find out where each capture endpoint puts the selector, starting from 0
landed = {}
for which in range(len(ins)):
    landed[which] = phase(n, "capture endpoint #%d, selector forced to 0" % which,
                          from_zero(which))
    n += 1
print("\n  capture endpoint -> selector position: %s\n"
      % {k: "%d (%s)" % (v, NAMES.get(v, "?")) for k, v in landed.items()})

# the open question: start from a value this endpoint is NOT, and see what crosses the wire
target = next((w for w, v in landed.items() if v != 2), 0)
start = 2 if landed.get(target) != 2 else 0


def asymmetry():
    vw(0x36, start)
    time.sleep(0.4)
    return run_stream("in", target, None, False)


phase(n, "capture endpoint #%d from selector %d  <-- the open question" % (target, start),
      asymmetry)
n += 1

phase(n, "capture endpoint #%d exclusive 48000" % target,
      lambda: (vw(0x36, 0), time.sleep(0.4), run_stream("in", target, 48000, True))[2]); n += 1
phase(n, "restore and idle",
      lambda: (vw(0x36, 0), time.sleep(2.0), "selector back to 0")[2])

print("\nend %s UTC   selector now %d (%s), phantom off"
      % (now(), sel(), NAMES.get(sel(), "?")))
one.close()

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"phases": phases, "endpoint_to_selector": landed,
               "asymmetry_test": {"endpoint": target, "forced_start": start}},
              f, ensure_ascii=False, indent=1)
print("phase log -> %s" % OUT)
