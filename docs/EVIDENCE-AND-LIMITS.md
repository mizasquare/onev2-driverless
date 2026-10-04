# How this was built, and what rests on what

**This project was vibecoded.** Essentially all of the code here — the patcher, the flasher, the
tests, the launchers — and most of the reverse engineering was produced by **Claude** (Anthropic's
Claude Opus 5, driving Claude Code). The human author owns the hardware, set the goals, made the
calls, ran every physical test and accepts the consequences — but does not claim the expertise to
audit every line of AVR32 reasoning independently, or to have enumerated every way this could go
wrong. Nobody with firmware-engineering credentials has reviewed it.

That is not a reason to dismiss this, and not a reason to trust it either. It is a reason to know
which parts rest on measurement and which rest on argument.

## Measured on real hardware, and reproducible by you

- Every descriptor change in [WHAT-THE-PATCH-CHANGES.md](WHAT-THE-PATCH-CHANGES.md), read field by
  field out of the images.
- Factory firmware genuinely fails on Windows 11's inbox driver — problem code 10, "this device
  cannot start". The patched firmware does not.
- Reading the firmware back off a device reproduces Apogee's own image files byte for byte, and
  rebuilding the patched images from those reproduces what was flashed, byte for byte.
- 26 automated checks and 5 physical long-press phases pass on the patched device.
- Record and play work on Windows 11, macOS and an M2 iPad over USB-C with no vendor software.

## Argued, not proven

- That the 136 bytes of firmware the code patch overwrites really are unreachable. Four independent
  arguments say so, deliberately chosen so none of them depends on a disassembler staying in sync
  with the instruction stream — but that is reasoning about a binary, not a proof, and no second
  expert has checked it. The bounded worst case if it is wrong is also an argument.
- What that dead code was *for*. Its behaviour is read off the instructions; its purpose is a
  guess, and is labelled as one.
- Anything in `docs/` marked a hypothesis. It is marked for a reason.

## Simply unknown

- Long-term behaviour. This firmware has run for days, not months. Nothing is known about flash
  wear, battery behaviour or thermal effects over time.
- Variation between units: two devices, one model, one factory firmware version (1.05).
- Whether patching from a Mac works at all. The patched firmware is verified on macOS; the Mac
  launcher, the Python bootstrap behind it and flashing from macOS have not been exercised. The
  flashing code is the same code the Windows path runs, and macOS needs no driver binding.

## Where your firmware comes from

**No firmware images are in this repository.** They are Apogee's. You get your own, from your own
device.

**Menu item 2 of the launcher reads the firmware out of your ONE** and writes the two files
everything else is built from. The device can read its own flash over the same channel used for
writing, and a stock image file turns out to be nothing but a 4-byte reset vector, zero padding,
and the bank's contents — so the files can be rebuilt exactly as Apogee shipped them.

Verified on hardware, not just on paper: a device rolled back to factory firmware was dumped, and
the rebuilt files match Apogee's own byte for byte —

```
ONEv2_USB_Audio_Image0.bin   sha256 e28421fef6df7cef41c39389d115573444a55aac88cecc49f6f17e1082b23e32
ONEv2_USB_Audio_Image1.bin   sha256 804d9d83fb5b3fcb58d08963e36e8e9488e99e3cafbd97299f691c228285f51f
```

— and building the patched images from those dumped files reproduces the images already validated
on the device, byte for byte again.

Each bank is judged on its own, so the backup tells you exactly what it found and will not pass
off a patched bank as a factory one. The patcher checks the files against known fingerprints and
refuses outright if they are not the firmware these patches were written and tested against. Keep
them somewhere off the computer as well.

### The other way: extract them from Maestro

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

## Authors

- **Sukwoon Song** — owns the hardware, set the goals, made the decisions, ran every physical
  test, and bears the consequences of publishing this.
- **Claude** (Anthropic's Claude Opus 5, via Claude Code) — the reverse engineering and
  essentially all of the code. Co-author on every commit in this repository.

Copyright for licensing purposes rests with the human author; MIT, see [LICENSE](../LICENSE).
