#!/usr/bin/env python3
"""Watch the ONEv2's own UI state from the outside while a human works the knob.

Why this exists: the firmware's button/encoder state machine is being traced in the disassembly,
and a trace needs an anchor. These two vendor reads give one for free:

    0xC0 0x48 wLength 1   GetEncoderSelect -- Apogee's own symbol name. What it actually contains
                          has never been measured; idle it reads 0x01.
    0xC0 0x29 wLength 6   GetHardwareChanges -- an EVENT QUEUE, not a snapshot: byte 2 carries a
                          value on the first read and zero afterwards, so a read CONSUMES it.
                          That is why the host app polled it, and why polling feeds the watchdog.

Read-only: nothing here writes to the device. Polling 0x29 does consume its events, which is the
only side effect and is exactly what the host app did.

Run it, then follow the prompts it prints. Each line of output is a CHANGE, labelled with the
gesture that was being asked for at that moment, so the log labels itself.
"""
import sys, os, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import onev2_flash as F

# (seconds, what to ask the human to do). Keep each long enough to act in without rushing.
SCRIPT = [
    (6, "nothing - hold still, this is the baseline"),
    (7, "turn the knob SLOWLY CLOCKWISE a few steps"),
    (7, "turn the knob SLOWLY COUNTER-CLOCKWISE a few steps"),
    (6, "PRESS the button once (short)"),
    (6, "PRESS the button once (short)"),
    (6, "PRESS the button once (short)"),
    (8, "LONG PRESS until the volume indicator starts blinking"),
    (6, "PRESS the button once (short) - mic indicator should light"),
    (7, "turn the knob a few steps (mic monitor volume)"),
    (6, "PRESS the button once (short) - instrument indicator should light"),
    (8, "LONG PRESS to return to normal gain mode"),
    (6, "nothing - final baseline"),
]
POLL = 0.05                                  # 20 Hz; EP0 handles this easily

one = F.open_one(3)


def rd(req, n):
    for _ in range(10):
        try:
            return one.rd(req, 0, 0, n)
        except Exception:
            one.reconnect()
    return None


def snap():
    return rd(0x48, 1), rd(0x29, 6), rd(0x36, 1), rd(0x34, 1), rd(0x3E, 1)


NAMES = ("0x48 encsel", "0x29 event", "0x36 input", "0x34 micgain", "0x3e instgain")
print(__doc__.split("Run it")[0])
print("=" * 78)
print("Follow each instruction as it appears. Only CHANGES are printed.\n")

prev = snap()
print("baseline: " + "  ".join("%s=%s" % (NAMES[i], prev[i].hex() if prev[i] else "?")
                               for i in range(5)))
print()
t_start = time.time()
events = collections.Counter()
log = []

for secs, what in SCRIPT:
    print("-" * 78)
    print(">>> %-62s  (%d s)" % (what.upper(), secs))
    t_end = time.time() + secs
    while time.time() < t_end:
        cur = snap()
        for i in range(5):
            if cur[i] is None or prev[i] is None:
                continue
            if cur[i] != prev[i]:
                # 0x29 self-clears, so a drop back to all-zero is the read consuming it, not news
                if i == 1 and cur[i][1:] == b"\x00" * 5 and prev[i][1:] != b"\x00" * 5:
                    continue
                line = "   %6.2fs  %-12s %s -> %s" % (
                    time.time() - t_start, NAMES[i], prev[i].hex(), cur[i].hex())
                print(line)
                log.append((what, NAMES[i], prev[i].hex(), cur[i].hex()))
                events[(what, NAMES[i])] += 1
        prev = cur
        time.sleep(POLL)

print("=" * 78)
print("\nchanges per gesture:")
for (what, field), n in sorted(events.items(), key=lambda kv: SCRIPT.index(
        next(s for s in SCRIPT if s[1] == kv[0][0]))):
    print("  %-56s %-12s x%d" % (what[:56], field, n))

print("\ndistinct values seen per field:")
vals = collections.defaultdict(collections.Counter)
for what, field, a, b in log:
    vals[field][b] += 1
for field in NAMES:
    if vals[field]:
        print("  %-12s %s" % (field, dict(vals[field])))

print("\nfinal: " + "  ".join("%s=%s" % (NAMES[i], prev[i].hex() if prev[i] else "?")
                              for i in range(5)))
one.close()
print("\nPaste everything above back to Claude.")
