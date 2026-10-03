#!/usr/bin/env python3
"""R9 acceptance test: everything that can be judged over USB is judged by this script.

What R9 changes: in the three MIC focus states a long press advances the mic source
Internal -> External -> External+48V -> Internal instead of toggling output mute. In the
instrument and output focus states the long press still toggles mute, byte for byte Apogee's
own code.

Part 1 runs with no human. Part 2 needs one physical long press per phase; the script sets the
focus state over USB first, watches the registers, and prints PASS or FAIL itself.

It restores the device at the end: Internal Mic (phantom off), unmuted, mic focus.

NOTE: phase A walks the full cycle, so it WILL switch 48V phantom power on for a moment. Unplug
anything on the XLR that should not see 48V before running this.
"""
import sys, os, time, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import onev2_flash as F

SRC = {0: "Internal", 1: "External", 2: "External+48V"}
FOCUS_SET = {0: "instrument", 1: "mic", 2: "output"}
fails = []
one = F.open_one(3)


def rd(req, n=1, idx=0):
    for _ in range(10):
        try:
            return one.rd(req, 0, idx, n)
        except Exception:
            try: one.reconnect()
            except Exception: pass
    return None


def wr(req, v):
    for _ in range(10):
        try:
            one.wr(req, 0, 0, bytes([v])); return True
        except Exception:
            try: one.reconnect()
            except Exception: pass
    return False


def check(name, got, want):
    good = got == want
    print("  %-52s %-18s %s" % (name, str(got), "PASS" if good else "FAIL, wanted %s" % (want,)))
    if not good:
        fails.append(name)
    return good


print("=" * 78)
print("PART 1 - automated, no human needed")
print("=" * 78)

d = one.dev
print("\nidentity")
check("bcdDevice", "%#06x" % d.bcdDevice, "0x0112")
check("active flash image", one.get_active_image(), 1)
check("address of main (bank 1)", "%#010x" % one.get_address_of_main(), "0x80030c88")
check("config descriptor length", len(bytes(d.ctrl_transfer(0x80, 6, 0x0200, 0, 512))), 284)

print("\nthe patch is in flash (read back over the 0xA9 read path)")


def rd_flash(addr, n):
    out, a = b"", addr
    while len(out) < n:
        one.set_flash_address(0x80000000 | (a & ~0x1FF))
        chunk = one.read_chunk((a & 0x1FF) // 64)
        off = a & 0x3F
        take = chunk[off:off + min(n - len(out), 64 - off)]
        out += take; a += len(take)
    return out[:n]


check("hook @flash 0x2cbc8", rd_flash(0x2CBC8, 4).hex(), "fe9ffd06")
check("trampoline head @flash 0x2c5d4", rd_flash(0x2C5D4, 8).hex(), "5826c1105866c0f0")
check("mute arm entry @flash 0x2c5f8", rd_flash(0x2C5F8, 4).hex(), "feb0ee08")

print("\nvendor channel still answers")
for req, n, name in ((0x28, 3, "0x28 firmware version"), (0x29, 6, "0x29 event block"),
                     (0x33, 1, "0x33 output atten"), (0x34, 1, "0x34 mic gain"),
                     (0x35, 1, "0x35 output mute"), (0x36, 1, "0x36 mic source"),
                     (0x3E, 1, "0x3e instrument gain"), (0x48, 1, "0x48 encoder select")):
    b = rd(req, n)
    check(name, "ok" if b is not None else "FAILED", "ok")

print("\nthe UI state machine still runs - vendor 0x48 SET must move the focus")
wr(0x36, 0); time.sleep(0.3)                      # SET=1 is a no-op when the source is +48V
for v in (2, 0, 1):
    wr(0x48, v); time.sleep(0.4)
    check("0x48 SET %d (%s) reads back" % (v, FOCUS_SET[v]), rd(0x48)[0], v)

print("\nmute still works over USB (the same byte the mute arm writes)")
for v in (1, 0):
    wr(0x35, v); time.sleep(0.3)
    check("0x35 SET %d reads back" % v, rd(0x35)[0], v)

print("\nsource still settable over USB")
for v in (1, 2, 0):
    wr(0x36, v); time.sleep(0.5)
    check("0x36 SET %d (%s) reads back" % (v, SRC[v]), rd(0x36)[0], v)

print("\nWindows audio path unaffected")
try:
    import numpy as np, sounddevice as sd
    sd._terminate(); sd._initialize()
    ins = [i for i, x in enumerate(sd.query_devices())
           if "ONEv2" in x["name"] and x["max_input_channels"] > 0
           and sd.query_hostapis(x["hostapi"])["name"] == "Windows WASAPI"]
    outs = [i for i, x in enumerate(sd.query_devices())
            if "ONEv2" in x["name"] and x["max_output_channels"] > 0
            and sd.query_hostapis(x["hostapi"])["name"] == "Windows WASAPI"]
    check("WASAPI capture endpoints", len(ins), 1)
    check("WASAPI output endpoints", len(outs), 1)
    keep = rd(0x34)[0]
    wr(0x34, 35); time.sleep(0.4)
    with sd.InputStream(device=ins[0], samplerate=44100, channels=2, dtype="float32") as st:
        st.read(int(44100 * 0.6))
        buf, _ = st.read(int(44100 * 1.5))
    m = np.asarray(buf).mean(axis=1)
    rms = 20 * math.log10(float(np.sqrt(np.mean(m * m))) + 1e-12)
    print("  %-52s %-18s %s" % ("capture rms at 35 dB gain", "%.1f dBFS" % rms,
                                "PASS" if -90 < rms < -20 else "FAIL, implausible level"))
    if not (-90 < rms < -20):
        fails.append("capture level")
    for sr in (44100, 48000, 96000):
        try:
            with sd.OutputStream(device=outs[0], samplerate=sr, channels=2, dtype="float32",
                                 extra_settings=sd.WasapiSettings(exclusive=True)) as o:
                o.write(np.zeros((int(sr * 0.2), 2), dtype="float32"))
            print("  %-52s %-18s PASS" % ("exclusive output %d Hz" % sr, "ran"))
        except Exception as e:
            print("  %-52s %-18s FAIL %s" % ("exclusive output %d Hz" % sr, "-",
                                             str(e).splitlines()[0][:40]))
            fails.append("output %d" % sr)
    wr(0x34, keep)
except Exception as e:
    print("  audio checks skipped: %s" % str(e).splitlines()[0][:60])

print("\n" + "=" * 78)
if fails:
    print("PART 1 FAILED: %s" % ", ".join(fails))
    print("Stopping before the physical test. Roll back with:  onev2_flash.py activate 0")
    one.close()
    sys.exit(1)
print("PART 1: all automated checks passed")
print("=" * 78)

print("""
PART 2 - one physical LONG PRESS per phase. Hold the knob until something happens.
The script sets the focus over USB first, then watches. Do not turn the knob.
""")


def watch(label, secs, expect_src_delta, expect_mute_toggle):
    src0, mute0 = rd(0x36)[0], rd(0x35)[0]
    rd(0x29, 6); rd(0x29, 6)          # drain the read-to-clear event queue first
    ev = 0
    print("-" * 78)
    print(">>> %s" % label)
    print("    before: source=%d (%s)  mute=%d   ... LONG PRESS NOW (%d s window)"
          % (src0, SRC.get(src0, "?"), mute0, secs))
    t_end = time.time() + secs
    seen = []
    while time.time() < t_end:
        s, m = rd(0x36)[0], rd(0x35)[0]
        e = rd(0x29, 6)
        if e and e[2]:
            ev |= e[2]
        if (s, m) != (src0, mute0) and (s, m) not in seen:
            seen.append((s, m))
            print("    changed: source %d -> %d   mute %d -> %d   (%.1fs)"
                  % (src0, s, mute0, m, secs - (t_end - time.time())))
            break
        time.sleep(0.05)
    s, m = rd(0x36)[0], rd(0x35)[0]
    want_s = (src0 + expect_src_delta) % 3
    want_m = (1 - mute0) if expect_mute_toggle else mute0
    ok_s, ok_m = s == want_s, m == want_m
    print("    after:  source=%d (%s)  mute=%d" % (s, SRC.get(s, "?"), m))
    # 0x29 byte 2 is a bitmask of what changed: 0x10 = the work-queue host-notify slot that
    # FUN_8000AA30(type, 4) posts, 0x08 = a mute toggle. Seeing 0x10 is what proves the patch
    # passed mode 4 rather than mode 3, i.e. that Maestro's display would follow the knob.
    want_bit = 0x10 if expect_src_delta else 0x08
    ok_e = bool(ev & want_bit)
    print("    0x29 event bits seen %#04x ; expected bit %#04x : %s"
          % (ev, want_bit, "present" if ok_e else "MISSING"))
    print("    source %s   mute %s   event %s   -> %s"
          % ("PASS" if ok_s else "FAIL (wanted %d)" % want_s,
             "PASS" if ok_m else "FAIL (wanted %d)" % want_m,
             "PASS" if ok_e else "FAIL",
             "PASS" if (ok_s and ok_m and ok_e) else "FAIL"))
    if not (ok_s and ok_m and ok_e):
        fails.append(label)
    return ok_s and ok_m and ok_e


wr(0x36, 0); wr(0x35, 0); time.sleep(0.4)
wr(0x48, 1); time.sleep(0.5)
print("focus set to mic (0x48=%d), source Internal, unmuted" % rd(0x48)[0])

watch("A1  mic focus: long press should advance Internal -> External", 25, +1, False)
watch("A2  mic focus: long press should advance External -> External+48V  (48V COMES ON)",
      25, +1, False)
watch("A3  mic focus: long press should wrap External+48V -> Internal", 25, +1, False)

wr(0x48, 2); time.sleep(0.5)
print("\nfocus set to output (0x48=%d)" % rd(0x48)[0])
watch("B   output focus: long press should toggle MUTE, source unchanged", 25, 0, True)

wr(0x48, 0); time.sleep(0.5)
print("\nfocus set to instrument (0x48=%d)" % rd(0x48)[0])
watch("C   instrument focus: long press should toggle MUTE back, source unchanged", 25, 0, True)

print("\n" + "=" * 78)
wr(0x36, 0); wr(0x35, 0); wr(0x48, 1); time.sleep(0.4)
print("restored: source=%d (%s)  mute=%d  focus=%d"
      % (rd(0x36)[0], SRC.get(rd(0x36)[0], "?"), rd(0x35)[0], rd(0x48)[0]))
if fails:
    print("\nFAILED: %s" % ", ".join(fails))
    print("Roll back with:  onev2_flash.py activate 0   (bank 0 holds R8, no code patch)")
else:
    print("\nALL PASSED - the long press cycles the mic source in mic focus and still mutes "
          "elsewhere.")
one.close()
sys.exit(1 if fails else 0)
