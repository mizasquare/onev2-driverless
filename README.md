# Apogee ONE (2nd gen) — driverless firmware patches

This patches the firmware of the 2013 **Apogee ONE for iPad & Mac** (USB `0c60:0017`, product
string `ONEv2`) so that it

- records and plays on **Windows 11, macOS and iPad (USB-C)** with the drivers those systems
  already ship — no Apogee driver, no Apogee app;
- lets the **knob on the device** switch its own microphone input between Internal, External and
  External + 48 V, which previously only Apogee's software could do.

Vendor support for the ONE is winding down. The patch is deliberately small: the firmware's USB
description of itself, plus 82 bytes of code.

| Platform                                     | Record   | Play     | Input switching on the device |
| -------------------------------------------- | -------- | -------- | ----------------------------- |
| Windows 11, inbox `usbaudio2.sys`            | verified | verified | verified                      |
| macOS (M1 MacBook on Tahoe)                  | verified | verified | verified                      |
| iPad USB-C (iPad Pro M2 on iPadOS 27.2 beta) | verified | verified | verified                      |

On the iPad, Apogee's own Maestro app still drives the mixer and device controls over USB-C after
the patch — the class-compliant audio does not come at the cost of the vendor app.

> Apogee® and Apogee ONE® are trademarks of Apogee Electronics Corporation. This project is not
> affiliated with, authorised by, endorsed by or sponsored by Apogee Electronics Corporation.
> Those names appear here only to identify the hardware these patches are for. No Apogee firmware,
> software or documentation is redistributed in this repository.
>
> This is independent reverse engineering for interoperability, done on hardware the author owns.
> Patching your own device will void any remaining warranty. Everything here comes with no warranty
> of any kind — see [LICENSE](LICENSE).

---

## Patch it

You do not need to know any Python, or open a terminal. Two steps.

### Windows (tested but still try on your risk)

Windows needs to be told to let us reach the ONE's control channel, and **what you have to do
depends on which firmware the device is still running.** Find out first — this is read-only:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools\win-usb-state.ps1
```

It prints what Windows currently thinks the ONE is and tells you which of the cases below you are
in. (Menu item 1 runs it for you too.)

**Why it differs.** The firmware's own descriptor decides how Windows splits the device up. Factory
firmware declares interfaces 0–3 as one audio function, so Windows makes a *single* child device
for all four and loads the audio driver on it — which then fails, because interface 3 is not audio.
There is no separate node for interface 3, so there is nothing for WinUSB to attach to. The patch
corrects that declaration to interfaces 0–2, after which interface 3 becomes its own node.

| Your device | What Windows shows | What to do |
| --- | --- | --- |
| **Factory firmware** (never patched) | one node, audio driver, **problem 10**; no `MI_03` | bind WinUSB to the **composite parent** |
| **Already patched** | `MI_00` working as a sound card, plus `MI_03` | bind WinUSB to **`MI_03` only** |

**Factory firmware — bind the parent.** Run [Zadig](https://zadig.akeo.ie/) as Administrator →
**Options → List All Devices** → **Options → untick "Ignore Hubs or Composite Parents"** (without
this the parent is not in the list at all) → pick **`ONEv2 (Composite Parent)`**, USB ID
`0C60 0017` with no interface number → driver **WinUSB** → **Replace Driver**, and accept the
"you are about to modify a system driver" warning.

Audio stays dead while that binding is in place. It was already dead — that is the problem 10
above — so nothing is lost. **Undo it once you have patched:** Device Manager → Universal Serial
Bus devices → `ONEv2` → Uninstall device → tick **"Attempt to remove the driver for this
device"** → unplug and replug. Windows then drives the patched device as a sound card, and
interface 3 reappears as its own node.

**Already patched — bind interface 3.** Zadig as Administrator → **Options → List All Devices** →
pick **`iAP Interface (Interface 3)`** → **WinUSB** → Install.

> **Pick interface 3 and nothing else** in this case. Interface 0 is the sound card; binding
> WinUSB to it takes the audio away until you undo it in Device Manager.

What "signed" means here: Zadig/libwdi generates a **self-signed** catalog and installs its own
certificate, so Windows accepts it without test-signing mode. It is not a vendor or WHQL
signature. There is no Apogee-supplied Windows driver for this device that we have found.

Then **double-click `PATCH-ME-WINDOWS.bat`.**

### macOS (untested. try on your risk)

**Double-click `PATCH-ME-MAC.command`.** Nothing to install first; macOS lets us reach the control
interface directly.

If Finder says it "cannot be opened because it is from an unidentified developer", right-click the
file → **Open** → **Open**. That happens to anything downloaded rather than cloned, once.

### iPad

Not possible from the iPad itself — iOS gives third-party code no way to open the control
interface directly. Patch from a PC or a Mac; the result then works on the iPad.

Apogee's own iPad Maestro app is a different matter, and it keeps working. See
[below](#apogees-own-software-still-works).

### What the launcher does

It finds Python, offers to install it if it is missing, puts the two USB packages it needs into a
`.venv` folder inside the project (your system Python is left alone), and opens a menu:

```
   1)  Check my device                    (reads only)
   2)  Back up my firmware                (reads only -- do this first)
   3)  Build the patched images           (does not touch the device)
   4)  Flash it and switch over           (WRITES the device)
   5)  Test it                            (reads only, asks you to press the knob)
   6)  Go back to the other firmware slot (the undo button)
   ?)  What do I do? Read this first
```

Work down the list. **Do not skip 2** — that is what saves the firmware currently on your ONE, and
it is your way back. Only item 4 writes anything to the device.

Item 5 runs 26 checks by itself and then asks you for five long presses, deciding pass or fail for
each from what the device reports. Stay at the device while it runs.

**Read [SAFETY.md](SAFETY.md) before item 4.** It is short. Two things in it matter more than the
rest: the patch is reversible because the device has two firmware slots and only the unused one is
ever written, and after patching **a long press can switch 48 V phantom power on** — unplug
anything on the XLR that should not see it.

---

## Where your firmware comes from

**No firmware images are in this repository.** They are Apogee's. You get your own, from your own
device:

**Menu item 2 reads the firmware out of your ONE** and writes the two files everything else is
built from. The device can read its own flash over the same channel used for writing, and a stock
image file turns out to be nothing but a 4-byte reset vector, zero padding, and the bank's
contents — so the files can be rebuilt exactly as Apogee shipped them.

Verified on hardware, not just on paper: a device rolled back to factory firmware was dumped, and
the rebuilt files match Apogee's own byte for byte —

```
ONEv2_USB_Audio_Image0.bin   sha256 e28421fef6df7cef41c39389d115573444a55aac88cecc49f6f17e1082b23e32
ONEv2_USB_Audio_Image1.bin   sha256 804d9d83fb5b3fcb58d08963e36e8e9488e99e3cafbd97299f691c228285f51f
```

— and building the patched images from those dumped files reproduces the images already validated
on the device, byte for byte again.

Each bank is judged on its own, so the backup tells you exactly what it found and will not pass
off a patched bank as a factory one.

<details>
<summary>The other way: extract them from Maestro</summary>

1. Download Apogee's **Maestro 2.5C** package for the ONE (`One iPad & Mac 2.5C.dmg`) from
   Apogee's support pages.
2. Extract `ONEv2_USB_Audio_Image0.bin` and `ONEv2_USB_Audio_Image1.bin` from the
   `One Firmware Updater.app` bundle inside it.
3. Put both in `firmware/`.

Either way, this is what correct files look like:

```
ONEv2_USB_Audio_Image0.bin   98,488 bytes    linked for flash bank 0 at 0x80004000
ONEv2_USB_Audio_Image1.bin  229,560 bytes    the same body relocated +0x20000
both: bcdDevice 1.05, and a 340-byte config descriptor twice over
```

</details>

Keep those two files somewhere off the computer as well. The patcher checks them against known
fingerprints and refuses outright if they are not the firmware these patches were written and
tested against.

---

## What the patch changes

### The USB descriptor

The ONE exposes **four** USB interfaces: `0` AudioControl, `1` AudioStreaming out (playback),
`2` AudioStreaming in (capture), `3` Apogee's own iAP/vendor interface. The descriptor describing
all of that shrinks from **340 to 284 bytes**; the slot in flash is 340 bytes hard, so it had to.

Stock → patched, every change:

| Where | Field | Stock | Patched | Why |
| --- | --- | --- | --- | --- |
| Config | `wTotalLength` | 340 | 284 | follows from the rest |
| IAD | `bInterfaceCount` | 4 | **3** | the audio function is interfaces 0–2. Stock swallowed the vendor interface into it. |
| AC header | `wTotalLength` | 174 | **111** | stock was wrong by 7 — it counted the interrupt endpoint descriptor, which the spec excludes. 167 were actually there. |
| Clock source 1 | `bmAttributes` | `0x01` internal **fixed** | `0x03` internal **programmable** | the device runs several sample rates; a fixed clock contradicts the rate control it advertises |
| Clock source 1 | — | **declared twice**, both with ID 1 | the duplicate is gone | unit IDs must be unique |
| Feature unit 4 (playback) | `bLength` | 10 | **18** | ADC-2 §4.7.2.8 says `6 + (channels+1)×4`. 10 describes a 0-channel unit on a stereo path. |
| Feature unit 4 | `bmaControls` | `0f000000` (master only) | master + L + R, each `0f000000` | mute and volume, per channel, as the hardware actually has |
| Feature unit 10 (mic) | `bLength` | 10 | **18** | same defect |
| Feature unit 10 | `bmaControls` | `04000000` — volume, host-readable | all **zero** | the firmware does not implement a mic volume control. Claiming one made hosts ask and get nothing. |
| Input terminal 9 (mic) | `bmChannelConfig` | `0x00000000` | `0x00000003` | FRONT_LEFT \| FRONT_RIGHT |
| Capture `AS_GENERAL` | `bmChannelConfig` | `0x00000004` FRONT_CENTER | `0x00000003` | one spatial bit for a two-channel stream is malformed. **This is what iPadOS refused.** |
| Output terminal 8 | `bSourceID` | 15 (the selector) | **10** (the mic feature unit) | the capture path no longer runs through a selector unit |
| Selector unit 15 | — | 3 pins, `iSelector` = string **21** | **removed** | iPadOS cannot build a capture path through a selector unit at all. String 21 does not exist on this device either. |
| Input terminals 11, 13 | — | duplicate mic terminals | **removed** | the three mic sources are one terminal; switching between them is the device's business, not the host's |
| Feature units 12, 14 | — | their feature units | **removed** | same |
| Endpoint `0x01` (playback) | `bmAttributes` | `0x0d` Synchronous | `0x09` **Adaptive** | the device does not lock to USB SOF |
| Endpoint `0x82` (capture) | `bmAttributes` | `0x0d` Synchronous | `0x05` **Asynchronous** | it runs on its own clock |
| Device | `bcdDevice` | 1.05 | 1.12 | so you can tell which firmware is running |

The two stored copies of the descriptor are identical except that the patched second copy carries
`bMaxPower` 6 instead of 5 — a deliberate marker, so you can tell from the host side which copy
the device actually served.

The single change that mattered most was removing the selector unit: **iPadOS will not build a
UAC2 capture path through one.** Most of the rest is compliance tidying that Windows and macOS
tolerated and the iPad did not.

Not all of it was tolerated, though. A device rolled back to factory firmware and plugged into
Windows 11 reports the audio function with **problem code 10, "this device cannot start"** — the
inbox `usbaudio2.sys` rejects the stock descriptor outright. That is measured on hardware, not
inferred, and it is the plainest statement of why this project exists.

### Apogee's own software still works

Changing the IAD moved interface 3 out of the audio function, which is the correction that makes
Windows expose it separately — and which could plausibly have hidden it from Apogee's own software
instead. It did not.

Observed on an M2 iPad Pro: **Apogee's iPad Maestro app, written for the Lightning era, still
drives the mixer and the device controls over USB-C after the patch.** Apple's MFi/iAP path to
interface 3 is untouched, so the vendor app keeps working alongside the class-compliant audio —
you are not trading one for the other.

What *is* out of reach on iOS is opening interface 3 yourself: third-party code gets no direct
access to it, which is why the knob had to learn to switch the mic source in firmware rather than
being driven from a host app. The MFi route Apogee uses needs their entitlement, not just the
descriptor.

### The code — 82 bytes

Two writes:

```
hook         4 bytes at 0x8000CBC8   `rcall 0x8000A208`  ->  `bral 0x8000C5D4`
trampoline  78 bytes at 0x8000C5D4   inside state 7's handler, which is dead code
```

Stock behaviour: a long press (held 105 main-loop passes) toggles output mute, in any focus state.
Apogee's own knowledge base documents it — hold the knob to mute and unmute the output.

After the patch, the long press checks which indicator currently has focus:

- **microphone focus** (Internal / External / External + 48 V) — advance the mic source one step,
  wrapping round;
- **instrument or output focus** — toggle mute, running Apogee's own code byte for byte.

So mute stays reachable from the panel: short-press to the instrument or speaker indicator, then
hold. That also keeps an escape route if host software leaves the output muted.

The trampoline is not a blob pasted in from somewhere. The patcher **lifts Apogee's own mute code
out of your image**, retargets its three `rcall`s for your bank, appends a jump back, and checks
the result against a SHA-256 of the exact bytes that were validated on hardware. If your image
differs, the hash fails and nothing is written.

#### Why it is safe to overwrite state 7

The front panel is a state machine with a vtable of nine handlers at `0x8000C370`. Entry 7's
handler is 136 bytes long and **nothing can reach it**:

- the only 32-bit word in the whole 98,488-byte image pointing into that handler is the vtable
  entry itself, which the patch leaves alone;
- no 4-byte branch or call anywhere in the image resolves into the region — an algebraic scan of
  every even address finds zero hits — and no compact 2-byte branch in the neighbouring handlers
  does either;
- the constant 7 is never materialised inside the UI module, so nothing can store 7 into the focus
  variable: `mov Rd,0x7` appears 40 times in the image and 0 times in `0x8000C3B0..0x8000CD00`;
- all 36 instructions that address the focus variable at all are inside that same module.

These four arguments were chosen because none of them depends on a disassembler staying in sync
with the instruction stream — an earlier analysis pass desynced on the vtable (which is data) and
got this wrong, so the claim is made in ways that cannot fail the same way.

**What state 7 did** *(the code is established fact; what it was for is inference)*: its tick
handler paints bits 3/2/1/0 of a RAM byte onto four indicator ids; entering or leaving it blanks
all four and clears the mask; a press returns to state 6. That is an indicator-override display —
show an arbitrary combination of four lamps — and it is the fine-grained sibling of state 8,
"Identify", which lights everything. A diagnostic or annunciator display, most likely left over
from development. It is a *display*, not a producer: the status bits it would have shown are still
computed and still published to RAM by their one writer, so nothing host-visible is lost.

And if the region somehow were entered, the worst case is bounded: the focus value 7 passes both
comparisons, falls into the mic arm, advances the source once, and returns through a jump into a
correctly framed function. Wrong, not a crash — and that bound holds even if all four arguments
above were wrong.

58 of state 7's 136 bytes are still spare. 36 orphaned bytes after the hook are left exactly as
they were rather than filled with nops, so a diff against stock shows only what was deliberately
changed.

### Reproducible

`patch/patch_r9.py` builds the patched images from your stock images deterministically. Rebuilding
produces files byte-identical to the ones flashed and tested here, and it reports every byte it
changed — currently 488, with `bytes changed outside descriptor regions: 0` for the descriptor
rounds.

---

## If something goes wrong

**Menu item 6, "Go back"**, fixes almost everything: the device keeps two firmware slots and the
old one is still sitting there, so switching back is one command and one restart.

[SAFETY.md](SAFETY.md) covers the rest, including the one genuinely unrecoverable mistake — a
write at or above `0x80040000`, which aliases onto the bootloader's reset vector because the flash
address decode ignores bit 18 — and how the tools here refuse to make it.

---

## Licence

MIT, see [LICENSE](LICENSE).

---
---

# For tinkering further

Nothing below is needed to patch a ONE.

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
these. On Windows this needs WinUSB bound to `MI_03`; on macOS libusb reaches it directly; on iOS
third-party code cannot open the interface at all, which is why the code patch exists. Apple's
MFi/iAP path to the same interface does still work there — Apogee's own iPad app uses it and keeps
working after the patch — but that route is not open to anyone without their entitlement.

Apogee left a lot of the device's state readable and writable this way, which is presumably how
they debugged it, and it is why the whole front-panel model here could be established from outside
before any disassembly: `0x48` selects focus, `0x29` reports the events, and the rest read back
what each press did.

On the Windows side, Zadig/libwdi's catalog is self-signed
(`CN=USB\VID_0C60&PID_0017&MI_03 (libwdi autogenerated)`) and it installs its own certificate, so
Windows accepts it without test-signing mode. `usb/onev2_winusb.inf` binds the same inbox
`WinUSB.sys` to interface 3 by hand if you prefer that to Zadig — but note it names
`VID_0C60&PID_0017&MI_03`, which **only exists once the device is patched**. On factory firmware
the binding has to go on the composite parent instead, as the Windows section explains.

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

- [onev2-ui-state-machine.md](docs/onev2-ui-state-machine.md) — the front-panel state machine,
  every RAM variable and transition with its flash address, and the code patch in full
- [onev2-control-protocol-RE.md](docs/onev2-control-protocol-RE.md) — the vendor protocol
- [descriptor-diff-vs-knowngood.md](docs/descriptor-diff-vs-knowngood.md) — the descriptor, field
  by field, against a compliant reference
- [bootloader-dump-findings.md](docs/bootloader-dump-findings.md) — the stock Atmel DFU bootloader,
  why a watchdog reset does **not** reach it, and why there is no fallback for a bad application
- [FLASHING.md](docs/FLASHING.md) — the `0xA9` protocol in detail
- [mfi-iap-usbc-watchdog.md](docs/mfi-iap-usbc-watchdog.md) — MFi/iAP, the USB-C transition, and
  the ~9.11 s watchdog

Superseded, kept because the reasoning is part of the record:

- [CODE-PATCH-PLAN.md](docs/CODE-PATCH-PLAN.md) — a plan to hook the UAC2 class handler that turned
  out to be unnecessary; the firmware already answers class requests
- [ep0-map-verification.md](docs/ep0-map-verification.md) — includes a correction of a wrong
  refutation of mine, left visible on purpose
- [handoff-cloud-*.md](docs/) — briefs written for other analysis sessions
