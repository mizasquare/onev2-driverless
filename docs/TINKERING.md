# For tinkering further

Nothing here is needed to patch a ONE.

## The vendor control protocol

Flashing is **not DFU**. Vendor request `0xA9` goes to the running application, sub-command in
`wValue`, index in `wIndex`, all integers big-endian. Vendor `0xA7` is a soft reset. There are two
application banks and only the inactive one is ever written, so a bad image is one `activate` away
from being undone.

The control protocol was recovered from Apogee's own symbol names in their macOS updater binary:

| bRequest | Dir  | Len | Meaning                                                              |
| -------- | ---- | --- | -------------------------------------------------------------------- |
| `0x28`   | in   | 3   | firmware version / hardware id                                       |
| `0x29`   | in   | 6   | knob and button event block — **read-to-clear**, byte 2 is a bitmask |
| `0x33`   | both | 1   | output attenuation                                                   |
| `0x34`   | both | 1   | mic preamp gain, signed dB                                           |
| `0x35`   | both | 1   | output mute                                                          |
| `0x36`   | both | 1   | mic source: 0 internal, 1 external, 2 external + 48 V                |
| `0x3E`   | both | 1   | instrument gain                                                      |
| `0x48`   | both | 1   | which level the knob adjusts: 0 instrument, 1 mic, 2 output          |

`bmRequestType` is `0x40` out / `0xC0` in, recipient **device**, so `wIndex` is 0 for all of
these. On Windows this needs WinUSB bound to `MI_03` (see [WINDOWS-SETUP.md](WINDOWS-SETUP.md));
on macOS libusb reaches it directly; on iOS third-party code cannot open the interface at all,
which is why the code patch exists. Apple's MFi/iAP path to the same interface does still work
there — Apogee's own iPad app uses it and keeps working after the patch — but that route is not
open to anyone without their entitlement.

Apogee left a lot of the device's state readable and writable this way, which is presumably how
they debugged it, and it is why the whole front-panel model here could be established from outside
before any disassembly: `0x48` selects focus, `0x29` reports the events, and the rest read back
what each press did.

## Doing it from the command line

The launchers are a wrapper around these. Python 3.9+, `pyusb` with a libusb backend, plus
`sounddevice`/`numpy` for the test's audio checks.

```bash
pip install pyusb libusb-package sounddevice numpy

python usb/backup-stock.py                 # read your firmware out of the device
python patch/patch_r9.py                   # build the patched images from it

python usb/onev2_flash.py probe            # read-only: ids, descriptors, bank state
python usb/onev2_flash.py flash firmware/ONEv2_USB_Audio_Image0.R9.patched.bin \
                                firmware/ONEv2_USB_Audio_Image1.R9.patched.bin --yes
python usb/onev2_flash.py activate 1       # whichever bank the flash just wrote
python usb/r9-test.py                      # 26 automated checks + 5 guided long presses

python usb/onev2_flash.py activate 0       # the undo button
python usb/onev2_flash.py verify 1 firmware/ONEv2_USB_Audio_Image1.R9.patched.bin
python usb/onev2_flash.py dump 0x24000 0x140b8 bank1.bin
```

## Layout

```
PATCH-ME-WINDOWS.bat     double-click on Windows
PATCH-ME-MAC.command     double-click on macOS
tools/      menu.py            what the launchers open
            win-usb-state.ps1  read-only: what Windows thinks the ONE is, and what to do
patch/      patch_r9.py        the one to run; rounds 2..9, self-contained from stock images
            avr32asm.py        a small AVR32 assembler and an independent disassembler
            history/           rounds 2..8 on their own, for the record
usb/        backup-stock.py    read the firmware out of your own device
            onev2_flash.py     the 0xA9 flasher: probe, dump, flash, verify, activate
            r9-test.py         the acceptance test
            onev2_winusb.inf   bind WinUSB to interface 3 without Zadig
            knob-probe*.py     watch the UI state machine from outside while you work the knob
            rate-probe.py      which sample rates the device really runs
            selector-probe.py  whether the host drives the selector unit
            verdict.ps1        Windows device nodes, audio endpoints, usbaudio2 event history
            capture-classreq2.bat + exercise-classreq.py + parse-classreq.py
                               ETW capture of the UAC2 class requests, decoded
docs/       the reverse-engineering record
firmware/   where your own images go. Nothing here is committed.
```

## Documentation

Current:

- [WHAT-THE-PATCH-CHANGES.md](WHAT-THE-PATCH-CHANGES.md) — every descriptor field and the 82-byte
  code patch, with the reasoning for each
- [EVIDENCE-AND-LIMITS.md](EVIDENCE-AND-LIMITS.md) — what is measured, what is argued, what is
  unknown
- [WINDOWS-SETUP.md](WINDOWS-SETUP.md) — Zadig / WinUSB binding in detail
- [onev2-ui-state-machine.md](onev2-ui-state-machine.md) — the front-panel state machine, every RAM
  variable and transition with its flash address, and the code patch in full
- [onev2-control-protocol-RE.md](onev2-control-protocol-RE.md) — the vendor protocol
- [descriptor-diff-vs-knowngood.md](descriptor-diff-vs-knowngood.md) — the descriptor, field by
  field, against a compliant reference
- [bootloader-dump-findings.md](bootloader-dump-findings.md) — the stock Atmel DFU bootloader, why
  a watchdog reset does **not** reach it, and why there is no fallback for a bad application
- [FLASHING.md](FLASHING.md) — the `0xA9` protocol in detail
- [mfi-iap-usbc-watchdog.md](mfi-iap-usbc-watchdog.md) — MFi/iAP, the USB-C transition, and the
  ~9.11 s watchdog

Superseded, kept because the reasoning is part of the record:

- [CODE-PATCH-PLAN.md](CODE-PATCH-PLAN.md) — a plan to hook the UAC2 class handler that turned out
  to be unnecessary; the firmware already answers class requests
- [ep0-map-verification.md](ep0-map-verification.md) — includes a correction of a wrong refutation
  of mine, left visible on purpose
- `handoff-cloud-*.md` — briefs written for other analysis sessions
