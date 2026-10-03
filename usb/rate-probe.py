#!/usr/bin/env python3
"""Can Windows actually RETUNE this device's clock?

Why this is a test of class requests: the live descriptor declares CLOCK_SOURCE 1 with
bmAttributes 0x03 (internal PROGRAMMABLE) and bmControls 0x07 (sam-freq control read/WRITE).
Under UAC2 a host changes the rate only one way: a class request
  SET CUR, CS_SAM_FREQ_CONTROL, to the clock entity on the AudioControl interface.
In WASAPI *shared* mode the audio engine resamples, so any rate appears to work and proves
nothing. In *exclusive* mode the frames come from the device at the device's own clock, so a
second rate succeeding means something answered that class request.
"""
import sys, os, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import sounddevice as sd

RATES = [44100, 48000, 88200, 96000, 32000, 22050]

devs = [(i, d) for i, d in enumerate(sd.query_devices()) if "ONEv2" in d["name"]]
print("ONEv2 devices visible to PortAudio:")
for i, d in devs:
    api = sd.query_hostapis(d["hostapi"])["name"]
    print("  dev %-3d %-24s in=%d out=%d  default_sr=%s  %s"
          % (i, api, d["max_input_channels"], d["max_output_channels"],
             d["default_samplerate"], d["name"][:44]))

wasapi = [h["name"] for h in sd.query_hostapis()].index("Windows WASAPI")
ins  = [i for i, d in devs if d["max_input_channels"]  > 0 and d["hostapi"] == wasapi]
outs = [i for i, d in devs if d["max_output_channels"] > 0 and d["hostapi"] == wasapi]
print("\nWASAPI input devs %s   output devs %s" % (ins, outs))

for label, cand, check, Stream, kw in (
        ("INPUT",  ins,  sd.check_input_settings,  sd.InputStream,  dict(channels=2)),
        ("OUTPUT", outs, sd.check_output_settings, sd.OutputStream, dict(channels=2))):
    if not cand:
        print("\n=== %s: no WASAPI device ===" % label); continue
    dev = cand[0]
    for mode, extra in (("shared", None), ("exclusive", sd.WasapiSettings(exclusive=True))):
        print("\n=== %s dev %d, WASAPI %s ===" % (label, dev, mode))
        for sr in RATES:
            try:
                check(device=dev, samplerate=sr, extra_settings=extra, **kw)
                ok = "accepted"
            except Exception as e:
                print("   %6d Hz  rejected   (%s)" % (sr, str(e).splitlines()[0][:70]))
                continue
            # accepted: now actually open it and time the real frame rate
            try:
                t0 = time.perf_counter()
                with Stream(device=dev, samplerate=sr, dtype="float32",
                            extra_settings=extra, **kw) as st:
                    n = int(sr * 1.0)
                    if label == "INPUT":
                        st.read(n)
                    else:
                        st.write(np.zeros((n, 2), dtype="float32"))
                    dt = time.perf_counter() - t0
                print("   %6d Hz  %s + ran   1.00 s of frames took %.3f s wall  -> apparent %d Hz"
                      % (sr, ok, dt, int(n / dt) if dt > 0 else 0))
            except Exception as e:
                print("   %6d Hz  %s but OPEN FAILED (%s)" % (sr, ok, str(e).splitlines()[0][:70]))
