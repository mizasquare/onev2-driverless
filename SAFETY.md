# Read this before you flash anything

This writes firmware to hardware you own. Most of it is recoverable. Two things are not. Both are
listed first.

If you came here from the launcher's menu, the command lines below are what menu items 4 and 6
run for you — you do not have to type them. The one worth remembering is **menu item 6, "Go
back"**: it is the undo button, and it is almost always enough.

## The two that are not recoverable

**1. Never write at or above `0x80040000`.** Flash is 256 KB and the address decode on this part
**ignores bit 18**, so `0x80040000` aliases onto `0x80000000` — the bootloader's reset vector. One
page written there and the device needs JTAG, which means opening the case and soldering to a
100-pin TQFP. Measured, not theorised: `read(x)` and `read(x + 0x40000)` return byte-identical data
for every pair tested.

`onev2_flash.py` refuses any address outside `0x80000000`–`0x8003FFFF` and refuses a page that
crosses a bank boundary. That guard exists because an earlier version of it had an off-by-one that
would have allowed exactly this write.

**2. There is no DFU rescue for a broken application.** The stock Atmel bootloader is there
(`AT32UC3A3 DFU 1.0.3`, VID `0x03EB` / PID `0x2FF1`), but entering it needs a *non-watchdog* reset
with SRAM preserved **and** the key `0x4953504B` in SRAM — which only the running application can
arrange. A watchdog reset clears the key and runs the application. So if the application does not
start, USB is gone and JTAG is the only way back.

## What protects you

**A/B banks.** There are two application banks and `onev2_flash.py` only ever writes the
**inactive** one. The bootloader checks each bank's CRC against the value stored in the user page,
and runs the other bank on a mismatch. So:

- a **CRC-wrong** image never executes — you are protected automatically;
- a **CRC-right but functionally broken** image *does* execute, and that is the real risk.

Therefore: **always leave one bank on something you have already tested.** Flash, `activate`, test;
if it misbehaves, `activate` the other bank and you are back where you started, in one command.

```bash
python usb/onev2_flash.py activate 0     # or 1
```

Keep your stock images — menu item 2 is what produces them, and it is the one step not to skip.
`python patch/patch_r9.py` rebuilds every patched image from them deterministically at any time,
so the originals plus this repository are a complete restore path. Copy them somewhere off the
computer as well.

## 48 V phantom power

Round 9 makes a long press cycle the mic source, and the cycle reaches **External + 48 V**. A long
press can therefore switch phantom power on.

The cycle is **Internal → External → External + 48 V → Internal**, one step per hold. Read that
again if you use an external microphone, because the dangerous reading is the one that sounds
reassuring:

- from **Internal**, reaching 48 V takes two deliberate holds;
- from **External** — where you already are if an external mic is plugged in — **a single long
  press turns phantom power on.**

And on stock firmware a long press meant *mute*. So the gesture your hands already know is now the
one that can energise the XLR.

A ribbon microphone or an unbalanced source on the XLR can be damaged by phantom power. This is the
only change in this project that can harm equipment *outside* the ONE.

**How to avoid it.** The cycle only runs while the **mic indicator has focus**. Short-press to the
instrument or speaker indicator first and a long press still just toggles mute, exactly as before.
That is also the escape route if host software leaves the output muted.

**Making the cycle stop at External** is a reasonable thing to want, and it is a small code change
— but not the one-liner an earlier version of this file described, so here is the real position.
The wrap test is `cp.w r12, 0x3` in `build_trampoline`, and comparing against `0x2` instead is one
byte. Two things then bite:

- the trampoline's bytes are pinned by a SHA-256 that was validated on hardware, so any edit stops
  the build on purpose;
- the naive edit only wraps on *equality*, so a device sitting at External + 48 V would advance to
  source 3, which is out of range and whose behaviour nobody here has tested.

Doing it properly means changing the comparison to wrap on "2 or more", re-pinning the hash, and
re-running the acceptance test on hardware. If you want this, open an issue rather than patching
around the hash guard — it exists precisely so unvalidated trampolines do not reach flash, and
there is no USB rescue if one misbehaves.

`usb/r9-test.py` switches 48 V on while it runs. Unplug anything on the XLR that should not see it
before running the test.

## Smaller things worth knowing

- **Vendor request `0x28` takes `wLength` 3.** Asking for 4 returns an I/O error *and* kills the
  WinUSB handle, after which the device re-enumerates and every cached device index in your process
  is stale. If a script starts failing in confusing ways right after a vendor request, this is why.
- **`0x29` is read-to-clear.** Reading it consumes the event bits. Two readers racing will steal
  events from each other.
- **The descriptor slot is 340 bytes, hard.** Two config descriptors sit back to back at file
  `0x17614` and `0x17768` with a data table after them, so growing the first past 340 overwrites the
  second. Every descriptor round had to fit inside that.
- **Do not use the free tail at `0x800180B8`–`0x80020000`** without checking first. 32,584 bytes sit
  erased there, but whether Apogee's own updater pads or truncates its fixed write window is
  unverified, so an appended page may never reach flash. Round 9 deliberately uses dead code inside
  the existing image instead.
- **Flashing needs the vendor channel**, and on Windows what you bind depends on which firmware is
  running. On a **patched** device, bind WinUSB to **interface 3 and only interface 3** — binding
  it to interface 0 takes the audio away from `usbaudio2` until you undo it in Device Manager. On
  **factory** firmware there is no interface-3 node at all, because the stock descriptor declares
  interfaces 0–3 as one audio function; there the binding has to go on the **composite parent**,
  and it must be undone afterwards or the patched device will never appear as a sound card.
  `tools\win-usb-state.ps1` says which case you are in. This bit the author: rolling a device back
  to factory firmware on Windows locks you out of the vendor channel until you re-bind.

## If it goes wrong

1. **Menu item 6, "Go back"** — or `python usb/onev2_flash.py activate 0` (or `1`). Switch to the
   other bank. This is almost always enough.
2. Still broken: re-flash your stock images into the inactive bank, then activate it.
3. The device does not enumerate at all: the application is not starting. See reason 2 above —
   JTAG.

If you own two ONEs, keeping one on stock firmware is cheap insurance. The author no longer has
that second unit: its board was killed **after this work was finished**, converting its port to
USB-C — a soldering job, nothing to do with firmware. Nothing in this project has damaged a
device.

So it now runs on a single ONE, and what stands in for the spare is the **other flash bank holding
pristine factory firmware** plus backup image files kept off the machine. That is the arrangement
to copy if you only have one: back up before you patch, keep the files somewhere other than the
computer you patch from, and leave the bank you are not using on something you have already
booted.
