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

One step per hold, so Internal → +48 V takes two deliberate holds, never one. Even so: a ribbon
microphone or an unbalanced source on the XLR can be damaged by phantom power. This is the only
change in this project that can harm equipment *outside* the ONE.

If you would rather the cycle stopped at External and left 48 V to host software, that is a
two-byte change in `patch/patch_r9.py`: compare against `0x2` instead of `0x3` in the wrap test.

`usb/r9-test.py` switches 48 V on during phase A2. Unplug anything on the XLR that should not see
it before running the test.

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
   JTAG. Keeping a second unit on stock firmware is cheap insurance; the author did.
