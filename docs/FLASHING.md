# Flashing

How `usb/onev2_flash.py` writes the ONE, and what it refuses to do. You do not need this to patch a
device, the launcher runs it for you. If you run it by hand, read [SAFETY.md](../SAFETY.md) first.

The sequence was read out of Apogee's own macOS updater (x86_64, symbols intact) and has since been
run on two units. Flashing is **not DFU**: the device keeps its PID and never enters a bootloader mode.

## The channel

Vendor request `0xA9`, sent to the **running** device (`0c60:0017`). `bmRequestType` is `0x40` out
and `0xC0` in, recipient device, sub-command in `wValue`, index in `wIndex`, all integers big-endian.
On Windows this needs WinUSB on interface 3 ([WINDOWS-SETUP.md](WINDOWS-SETUP.md)).

| wValue | Dir | wIndex | Len | Name | Notes |
| ------ | --- | ------ | --- | ---- | ----- |
| 0 | out | 0 | 4 | SetFlashAddress | `0x80000000` + file offset |
| 1 | out | 0..7 | 64 | WriteChunk | eight chunks make one 512-byte page |
| 2 | out | 0 | 1 | CommitFlashPage | data `00` |
| 3 | in | 0..7 | 64 | ReadChunk | read-back |
| 4 | in | image | 4 | GetUserPageCRC | computed by the device |
| 5 | out | image | 4 | SetUserPageCRC | |
| 6 | in | 0 | 4 | GetActiveImage | the answer is byte 3 |
| 6 | out | image | 1 | SetActiveImage | data `00` |
| 7 | in | 0 | 4 | GetAddressOfMain | |

Vendor `0xA7` (out, one byte `00`) is a soft reset.

## Geometry

File offset X is flash `0x80000000 + X`. There are two app banks:

| Bank | Window written | Image file |
| ---- | -------------- | ---------- |
| 0 | `0x4000` to `0x20000` | `Image0.bin`, 98,488 bytes |
| 1 | `0x24000` to `0x40000` | `Image1.bin`, 229,560 bytes, the same body at +`0x20000` |

Each window is `0x1C000` long. The bootloader at `0x0` to `0x4000` is outside both, so a flash never
writes it. The 16 KB between the banks is unused.

Address decode ignores bit 18, so `0x80040000` aliases the bootloader's reset vector. The flasher
refuses any flash address outside `0x80000000` to `0x8003FFFF`. See [SAFETY.md](../SAFETY.md).

**Which bank gets written:** the one the device is not running from. The flasher decides by
GetAddressOfMain (below `0x80024000` means running bank 0, so write bank 1). If GetActiveImage
disagrees it warns and trusts the address, as Apogee's updater does.

## One flash, step by step

1. Refuse if more than one ONE is attached. The device re-enumerates during a write, and the flasher
   finds its own unit again by serial number, so a second unit could end up with half an image.
2. Check both files against the guards below.
3. For each 512-byte page of the file that falls inside the window: SetFlashAddress, 8 x WriteChunk,
   CommitFlashPage, 8 x ReadChunk, compare. A mismatch retries the page, up to 40 attempts. A lost
   handle is re-acquired and the page redone. About 11 seconds per bank. Only pages the file holds
   are written, the flasher does not pad to the window.
4. Read the CRC the device computed (GetUserPageCRC) and store it back (SetUserPageCRC). **This is
   what makes the bootloader launch the bank** instead of failing over to the other one. Refused if
   no page was written.
5. Stop. The device is still running the old bank. `activate N` does SetActiveImage and then a soft
   reset. `flash --activate` does both in one go, the launcher does not use it and asks you first.

Nothing signs an image. The only checks are the per-page read-back and a CRC the device computes
itself, so any bytes pass, including a broken image. That is why `SAFETY.md` says there is no USB
rescue for an image that boots into nothing.

## What the flasher refuses

- To write without `--yes`. `--dry-run` walks the whole sequence with no writes.
- A flash address outside `0x80000000` to `0x8003FFFF`, or a page outside the target window.
- A file that is not ONEv2 firmware at all. No override.
- A ONEv2 image that is not one of the four tested ones (factory bank 0 and 1, R9 bank 0 and 1, by
  SHA-256), unless you pass `--yes-i-built-this-image`.
- Overwriting the last bank that still holds factory firmware, unless you pass `--overwrite-factory`.
- A file shorter than its bank's start or longer than its end, which usually means the two image
  arguments were swapped.
- Running with assertions disabled (`python -O`), because much of the checking is written as `assert`.

## What rests on what

- **Read from Apogee's updater:** the sub-commands, the page sequence, the bank windows. That updater
  writes a fixed window (start `0x4000` or `0x24000`, length `0x1C000`) while both image files are
  shorter. Whether it pads or truncates is **unverified**, which is why this project does not rely
  on the free tail past the end of each image.
- **Measured on hardware:** flashing, read-back, activate and rollback on two units
  ([EVIDENCE-AND-LIMITS.md](EVIDENCE-AND-LIMITS.md) says how far that goes). Reads at `x` and
  `x + 0x40000` returning identical data, on five address pairs.
- **Not known:** how any of this behaves on a firmware version other than 1.05.
