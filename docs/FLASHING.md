# ONEv2 — flashing path & safety (from Mac updater disassembly)

> **CORRECTED 2026-10-02 — read `win-flash/README.md` instead for the flash mechanism.**
> The "vendor DFU" framing below is wrong for the ONE. Re-disassembling the real entry point
> `oneFirmwareUpdateFromFile` shows the ONE never enters DFU mode: flashing is vendor request
> **0xA9** against the *running* device (`0c60:0017`), with no PID change and no re-enumeration.
> The ApoUSB DFU code (and the PID `0x8017` claim) does not apply to this product — the
> Thesycon INF's "Apogee DFU" is PID `0x8016`, the Duet's. The *geometry* and *safety* claims
> below (inactive bank only, start `0x4000`/`0x24000`, length `0x1C000`, bootloader `0x0-0x4000`
> never written, page read-back verification, no image signature) were re-verified and still
> hold.

Interoperability/repair on the owner's own device. Flashing uses the device's OWN vendor DFU
mechanism (Apogee updater). All facts below are **[C]** confirmed by disassembling
`One Firmware Updater` (Mac, x86_64) unless tagged **[I]**.

## Flash geometry — the safety-critical part [C]

`oneFirmwareUpdate` (0x10000632b):
- reads active image index via vendor cmd **0xA9 sub-6** (`getActiveImage`) and the running main
  address via **0xA9 sub-7** (`getAddressOfMain`).
- writes the **inactive** bank only. Write start = **0x4000** (bank0) or **0x24000** (bank1);
  end = start + **0x1C000**. So it writes the app region `0x4000–0x20000` or `0x24000–0x40000`.
- **The bootloader/DFU region `0x0–0x4000` is NEVER written.** This is the guarantee the
  recovery plan relies on.
- after writing, switches the active image (`setActiveImage`) and reboots (`softReset`).
- each page is verified by read-back ("Flash page did not match. Retrying flash write."); a
  byte-modified image passes as long as the device accepts what it is sent (no separate
  whole-image signature was found; the tail 4 bytes are not a content checksum).

File→flash mapping is identity on `0x4000–0x20000` (must be, or stock images wouldn't boot), so
a patch at file offset X (within that range) lands at flash `0x80000000+X`. Our R2 patch at file
`0x1107c` → flash `0x8001107c` = the WDT CTRL literal. Correct.

## DFU entry & recoverability [C mechanism, I bootloader fallback]

- DFU entry is **app-triggered**: `EnterDFU` sends a control request (byte 0x21) to the RUNNING
  device, which re-enumerates to the DFU identity (PID 0x8017). **The app must run to enter DFU.**
- Therefore: if a flashed app still boots and answers USB, it is always re-flashable. The R2
  patch does not touch boot/USB/clock code, so the app runs normally → fully recoverable.
- Unknown [I]: whether the bootloader offers an independent DFU entry (button-at-power-on) or
  auto-falls-back to the other bank if the active app is invalid. We don't have the bootloader
  image. So treat "app that fails to enumerate" as the dangerous outcome.
- Backstops: (1) bootloader never overwritten; (2) dual bank — keep one bank stock; (3) a second
  physical unit as spare.

## Risk ladder

- **R2-only patch (WDT disable):** app boots and runs unchanged apart from the watchdog →
  safe first flash, validates the whole pipeline. **Start here.**
- **R1/R3 (descriptor/selector) patches:** can affect enumeration. Flash only after R2 proves the
  pipeline, keep the other bank stock, and keep the spare unit untouched until proven.

## How to flash (two paths)

### Path A — Apogee's own updater with a patched image (recommended for the first flash)
Lowest risk: reuses Apogee's tested flash sequence; the updater does NOT checksum the .bin file,
it just writes its bytes.
1. Take Apogee's `One Firmware Updater.app` (Intel Mac; Apogee says Intel + older macOS).
2. Replace `Contents/Resources/ONEv2_USB_Audio_Image0.bin` and `...Image1.bin` with our patched
   copies (`*.patched.bin`).
3. Force an update: bump `Contents/Resources/OneUpdaterVersions.plist` `firmware_version`
   above the device's (device reports 1.5.0 via vendor 0x28), e.g. to `1.5.1`. Otherwise the
   updater shows "All Firmware Up to Date" and does nothing.
4. Run it; it flashes the inactive bank and switches. Watch for a DFU error (non-destructive =
   device rejected the image) vs success.
Note: the Windows updater path (if located) avoids the Intel-Mac requirement; TBD.

### Path B — our own libusb flasher (later, for fine control)
We have the full vendor DFU protocol (EnterDFU req 0x21 → StartDFU → WriteDFUBlock(offset,buf,len)
→ page-verify → EndDFU/SetImageType/SetRevertId → softReset) and the 0xA9 management sub-commands.
A ~150-line pyusb tool could flash a chosen bank with exact bytes and let us flash ONE bank while
keeping the other stock. Higher control, but we implement the sequence, so do this only after
Path A proves the device accepts a modified image.

## Open items before a real flash
1. Confirm the device accepts a byte-modified image (first Path-A attempt answers this; rejection
   is non-destructive).
2. Locate/confirm a bootloader-level recovery (button-at-boot?) for the worst case — or accept the
   spare-unit backstop.
3. Windows updater availability (to avoid the Intel-Mac requirement).

## Current patched artifacts
- `ONEv2_USB_Audio_Image0.patched.bin`, `ONEv2_USB_Audio_Image1.patched.bin` — R2 only (WDT
  disabled): 2 bytes changed per bank at file 0x1107f/0x11083 (bank0) and +0x20000 (bank1),
  `0x..001301 → 0x..001300` (CTRL EN bit cleared). Verified by re-disassembly.
