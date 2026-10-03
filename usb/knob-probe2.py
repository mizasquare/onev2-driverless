#!/usr/bin/env python3
"""knob-probe round 2 — settle what the knob adjusts in monitor-volume (blinking) mode.

What round 1 established, from two runs:
  0x48 GetEncoderSelect has exactly three values and a short press cycles them 02 -> 01 -> 00 -> 02.
       0x48 = 1  the knob moved 0x34 mic gain        (event bit 0x02)
       0x48 = 0  the knob moved 0x3E instrument gain (event bit 0x04)
       0x48 = 2  the knob moved something unread     (event bit 0x01)
  0x29 byte[2] is a BITMASK of what changed, and reading consumes it.
  A long press raises event bit 0x08 and changes NOTHING else — so monitor-volume mode is NOT in
  0x48 (it has no fourth value). It lives in a RAM byte we cannot see from here.

Then Apogee's own knowledge base settled what the long press is, and it is not a monitor-volume
mode at all: "Hold down the knob for a few seconds. This mutes and unmutes the output."
(knowledge.apogeedigital.com/the-light-is-flashing-on-my-one-and-i-cant-hear-anything). The
blinking indicator means MUTED. Round 1 could not see it because it never read 0x35 OutputMute.

So this round reads the registers round 1 was blind to, to confirm or break that model:
  1. does a long press toggle 0x35 OutputMute, one-for-one with event bit 0x08?
  2. with 0x48 = 2, does the knob move 0x33 (output attenuation)?
  3. while muted, does everything else behave exactly as unmuted -- short press still cycling 0x48,
     the knob still moving 0x34 / 0x3E? If so there is no separate mode state at all, and the gate
     for the planned patch is simply 0x48 == 1.
  4. does 0x4C (mixer fader) ever move from the knob? If it never does, the monitor-mixer idea is
     dead and the knob only ever touches 0x33 / 0x34 / 0x3E.

Every phase ends by printing ALL current values, so state is visible even when nothing changed.
Read-only. Lengths were discovered defensively first: every request below answers at the length
used here. Reading 0x29 consumes its event bits, which is what Apogee's own host app did.
"""
import sys, os, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import onev2_flash as F

# (bRequest, wIndex, wLength, label)
REGS = [(0x48, 0, 1, "encsel"), (0x29, 0, 6, "event"), (0x35, 0, 1, "OUTMUTE"),
        (0x33, 0, 1, "outatten"), (0x34, 0, 1, "micgain"), (0x3E, 0, 1, "instgain"),
        (0x4C, 0, 1, "fader0"), (0x4D, 0, 1, "pan0")]

SCRIPT = [
    (8,  "NOTHING - baseline. Note which icon is lit and whether anything is blinking."),
    (10, "turn the knob a few steps."),
    (8,  "PRESS once. Wait, do not turn."),
    (10, "turn the knob a few steps."),
    (8,  "PRESS once. Wait."),
    (10, "turn the knob a few steps. (By now all three encoder positions are covered.)"),
    (12, "LONG PRESS. Expect: output MUTES and an indicator starts BLINKING."),
    (10, "NOTHING - just confirm the blinking. Is playback silent?"),
    (10, "while MUTED: PRESS once. Does the lit icon still change?"),
    (12, "while MUTED: turn the knob a few steps."),
    (10, "while MUTED: PRESS once again."),
    (12, "while MUTED: turn the knob a few steps."),
    (12, "LONG PRESS again. Expect: UNMUTES and the blinking stops."),
    (8,  "NOTHING - final baseline."),
]
POLL = 0.06

one = F.open_one(3)


def rd(req, idx, n):
    for _ in range(8):
        try:
            return one.rd(req, 0, idx, n)
        except Exception:
            try: one.reconnect()
            except Exception: pass
    return None


def snap():
    return tuple(rd(r, i, n) for r, i, n, _ in REGS)


def show(s, prefix="    "):
    print(prefix + "  ".join("%s=%s" % (REGS[k][3], s[k].hex() if s[k] else "?")
                             for k in range(len(REGS)) if REGS[k][3] != "event"))


print(__doc__)
print("=" * 78)
prev = snap()
print("baseline:"); show(prev)
t0 = time.time()
log = []

for secs, what in SCRIPT:
    print("-" * 78)
    print(">>> %s" % what)
    print("    (%d s)" % secs)
    t_end = time.time() + secs
    while time.time() < t_end:
        cur = snap()
        for k in range(len(REGS)):
            if cur[k] is None or prev[k] is None or cur[k] == prev[k]:
                continue
            name = REGS[k][3]
            if name == "event" and cur[k][1:] == b"\x00" * 5 and prev[k][1:] != b"\x00" * 5:
                continue          # the read clearing it is not news
            print("   %6.2fs  %-9s %s -> %s" % (time.time() - t0, name,
                                                prev[k].hex(), cur[k].hex()))
            log.append((what, name, prev[k].hex(), cur[k].hex()))
        prev = cur
        time.sleep(POLL)
    show(prev, "    end: ")

print("=" * 78)
print("\nwhich register moved during which gesture:")
agg = collections.Counter((w, n) for w, n, a, b in log)
order = {s[1]: i for i, s in enumerate(SCRIPT)}
for (w, n), c in sorted(agg.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][1])):
    print("  %-62s %-9s x%d" % (w[:62], n, c))

print("\nevent bitmask values seen (0x29 byte 2):")
bits = collections.Counter(b[4:6] for w, n, a, b in log if n == "event")
print("  " + ", ".join("0x%s x%d" % (v, c) for v, c in sorted(bits.items())))
one.close()
print("\nPaste everything above back to Claude.")
