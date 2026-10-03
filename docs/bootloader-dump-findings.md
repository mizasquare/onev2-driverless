# The bootloader, finally: it is Atmel's stock UC3 DFU bootloader

`resources/ONEv2_bootloader_0x0-0x4000.bin` — 16,384 bytes,
sha256 `a6710b27d40375607fe333436ab6cab061427c973680485e96fdc50e9e1a6e68`, ~8.7 KB of real content
(7,618 bytes are erased `0xFF`). Read off the live device with our own flasher, stable across
re-reads of four separate pages.

## How we got it

Flash is 256 KB and the address decode ignores bit 18, so `0x40000..0x80000` aliases onto
`0x0..0x40000`. The vendor `0xA9` read sub-command happily reads the whole space — including the
bootloader region `0x0..0x4000`, which the firmware update files never contained. Nothing was
written.

## What it is [C]

| field | value |
|---|---|
| product string | **`UC3A3 DFU 1.0.3`** (UTF-16LE at `0x1cb2`) |
| manufacturer string | **`ATMEL`** (at `0x1d20`) |
| device descriptor (`0x1d0c`) | `12 01 0002 00 00 00 40 EB03 F12F 0010 01 02 00 01` |
| → idVendor / idProduct | **`0x03EB` (Atmel) / `0x2FF1`** |
| → bcdDevice | `0x1000` |
| config descriptor (`0x1cf0`) | 27 bytes, 1 interface, self-powered, 100 mA |
| interface (`0x1cf9`) | `bInterfaceClass 0xFE / SubClass 0x01 / Protocol 0x02` = **DFU mode** |
| DFU functional descriptor (`0x1d02`) | `09 21 0F 0000 FFFF 0101` |
| → bmAttributes `0x0F` | willDetach + manifestationTolerant + canUpload + canDnload |
| → wTransferSize | `0xFFFF` |
| → bcdDFUVersion | `0x0101` = **DFU 1.1** |

So the ONEv2's bootloader is **not** an Apogee creation: it is Atmel's standard UC3 USB DFU
bootloader, presenting itself as `03EB:2FF1` over the standard USB DFU class.

It also does **not** match the first `0x4000` bytes of the update file (1166/16384 bytes equal).
The file's offset 0 holds `e08f2000` = `BR{al} 0x80004000`, a reset trampoline; the real device
has entirely different code there. Correction to an earlier note: that trampoline was a property
of the *file*, never of the device.

## Why this matters

It answers the question that has gated every risky step in this project — "if a flashed image
fails to enumerate, can we recover?" — and the answer is much better than we assumed:

- Our own flasher and Apogee's updater both need the **running application** to answer vendor
  `0xA9`/`0x21`. An image that fails to boot or enumerate is unreachable by either.
- But the bootloader is an **independent, standard DFU device**. If the chip can be made to enter
  it, recovery needs no working application at all, and standard tooling speaks to it
  (`dfu-util`, `dfu-programmer`, Atmel `batchisp`) — no Apogee software, no Intel Mac.

## Cloud BOOTLOADER_DFU_MAP verified locally (2026-10-02)

The cloud session's map was re-checked against these bytes. **Every point I could test holds.**

- All 15 quoted byte sequences are present at the quoted addresses, exactly.
- Every 2-byte branch in the reset decision, hand-decoded from Format I (bits 15..12 `1100`,
  bits 11..4 signed `disp8` in halfwords, bit 3 `0`, bits 2..0 `cond3`), matches their claim:
  `0x80000068 c0c3 → 0x80000080`, `0x8000007a c443 → 0x80000102`,
  `0x8000007e c481 → 0x8000010e` (`ne`), `0x80000100 cc02 → 0x80000080`.
  (`0x800022c2 c008` has bit 3 set, so it is not a Format-I branch — it is `RJMP .`, an infinite
  loop, as they said.)
- The key really is `0x4953504B`: `MOV R1,0x504b` + `ORH R1,0x4953`, ASCII `ISPK`.
- Launcher literals confirm the app bases and the user-page slots: `0x8000228c` and `0x800022c8`
  hold `0x80004000`; `0x80002238` holds `0x808001f4`; `0x8000223c` holds `0x808001f8`.
- The reset-path `LDDPC PC` literal at `0x8000014c` is `0x80002000`, a bootloader second stage —
  not the application base, which is the correction the cloud made mid-analysis.
- Full iProduct string is `AT32UC3A3 DFU 1.0.3` (at `0x1caa`); the earlier note here read it from
  `0x1cb2`, mid-string.

### But its recommended pre-flight check is impossible with our tools [C]

The map says to read `0x808001FC` off the unit through the application's `0xA9` read path, to learn
whether a hardware GPIO recovery pin is configured. **That does not work.** Reading
`0x80800000..0x808001FF` through `0xA9` returns **all `0xFF`**, while the device's own `0xA9`
CRC getter simultaneously returns real stored values (`0xf2c66499` / `0x4430e580`), and the
bootloader's own literals prove those values live in the user page at `0x808001F4/F8`. By
contradiction, the user page is not blank and **our `0xA9` read path cannot address it** — it is not
simply masking low bits either, since offset `0x1C0` holds real content in the bootloader region.

So **"is there a hardware recovery pin on these units?" is currently unanswerable**, and that pin is
exactly what the worst-case recovery story depends on. Treat it as absent until proven otherwise.

### The safety measure that follows

Because an application that boots but fails to enumerate cannot be reached by any tool we have, the
escape hatch should be built **into the patch itself**: have the patched firmware store
`0x4953504B` at SRAM `0x00000000` early in its startup. Then any watchdog reset — which the
application already arms at ~9.11 s in `main()` — lands in the bootloader's DFU mode instead of
re-running the broken image. That converts the one unrecoverable failure mode into a recoverable
one, provided the failure lets the watchdog fire. Open question before relying on it: whether
address `0x00000000` is used by the application's own `.data`/`.bss`, and what normally pets the
watchdog (the device runs for hours on macOS, so something does).

Note the CRC gate is **not** a "try it once" mode: if the stored CRC does not match, the launcher
flips to the other bank and runs that instead, so a non-matching image never executes at all.

## What is still unverified [H / open]

1. **How to enter the bootloader.** Stock Atmel UC3 bootloaders enter ISP/DFU on a configurable
   condition at reset — typically a GPIO level, and/or a force-ISP word in the UC3 user page, and
   generally also when the application area fails its check. We now have the bootloader bytes, so
   this is answerable by disassembling it; it has not been done. **Do not treat recovery as proven
   until the entry condition is identified and, ideally, demonstrated.**
2. **Whether the bootloader validates the app and self-selects DFU.** The application's user-page
   CRC (`0xA9` sub-commands 4/5) exists, which is suggestive, but the bootloader's use of it is
   unconfirmed.
3. **The exact part number.** The bootloader string says **UC3A3**, while a forum reader reported
   `32UC3A4` from PCB photos. Flash is confirmed 256 KB by the aliasing measurement, which fits
   `AT32UC3A3256` and `AT32UC3A4256` alike. Not resolved; do not state one as fact.
4. Writing to `0x20000..0x24000` (the 16 KB gap between the two banks, confirmed erased and
   readable) is **untested** — only reads have been exercised there.
