#!/usr/bin/env python3
"""Control experiment. Before crediting the host with driving the selector, check whether the
firmware moves the value by itself with NO audio stream open at all. An earlier observation in
this project (input type seen changing 0->1 between two probes) says it might."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import sounddevice as sd
import numpy as np
import onev2_flash as F

NAMES = {0: "Internal", 1: "External", 2: "Ext+48V"}
one = F.open_one(3)


def vr(req, n=1):
    for _ in range(12):
        try: return one.rd(req, 0, 0, n)
        except Exception: one.reconnect()
    raise IOError(hex(req))


def vw(req, v):
    for _ in range(12):
        try: one.wr(req, 0, 0, bytes([v])); return
        except Exception: one.reconnect()
    raise IOError(hex(req))


print("=== A: force 0, then NO stream for 20 s, poll twice a second ===")
vw(0x36, 0); time.sleep(0.3)
seq, t0 = [], time.time()
while time.time() - t0 < 20:
    seq.append(vr(0x36)[0]); time.sleep(0.5)
runs = [(v, sum(1 for _ in g)) for v, g in __import__("itertools").groupby(seq)]
print("  sequence: %s" % " ".join("%d x%d" % (v, n) for v, n in runs))
drift_a = len(runs) > 1
print("  -> %s" % ("DRIFTS with no stream: the firmware changes it itself" if drift_a
                   else "stable at 0 with no stream open"))

print("\n=== B: force 0, then open ONE stream on each endpoint, polling throughout ===")
devs = [i for i, d in enumerate(sd.query_devices())
        if "ONEv2" in d["name"] and d["max_input_channels"] > 0
        and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI"]
for dev in devs:
    vw(0x36, 0); time.sleep(0.4)
    pre = vr(0x36)[0]
    marks = []
    with sd.InputStream(device=dev, samplerate=44100, channels=2, dtype="float32") as st:
        for _ in range(8):
            st.read(2048)
            marks.append(vr(0x36)[0])
    post = vr(0x36)[0]
    print("  dev %-3d pre=%d  during=[%s]  post=%d" % (dev, pre, " ".join(map(str, marks)), post))

print("\n=== C: does it hold at 1 and 2 with no stream? ===")
for v in (1, 2):
    vw(0x36, v); time.sleep(0.3)
    s = [vr(0x36)[0] for _ in range(8) if not time.sleep(0.5)]
    print("  forced %d (%-8s) -> %s" % (v, NAMES[v], s))

vw(0x36, 0); time.sleep(0.3)
print("\nrestored input=%d (%s) -- phantom off" % (vr(0x36)[0], NAMES[vr(0x36)[0]]))
one.close()
