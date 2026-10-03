# Handoff: map the ONEv2 EP0 control-request pipeline so a UAC2 class handler can be inserted

You are picking up a firmware reverse-engineering project at a specific, well-defined point.
Almost everything below is already **confirmed**; your job is one remaining piece. Please do not
redo the finished work, and please mark every statement you produce as **[C] confirmed** (you read
it in the bytes / in the decompiler / in an authoritative doc — say which) or **[H] hypothesis**.
A past round of this project was set back by an unlabeled inference presented as fact, so this
matters more than speed.

---

## 1. What this is and what has been achieved

**Device:** Apogee ONE 2nd generation ("ONEv2"), USB `0c60:0017`, a 2013-era USB audio interface
(2 in / 2 out, built-in mic, external mic with 48 V phantom, instrument input, encoder knob,
OLED). Vendor support is winding down. The owner has two units and wants the device to keep
working with **no vendor driver and no host-side helper application** on Windows, macOS and
iPad (USB-C). iPad is the critical platform because host-side rescue (drivers, daemons, libusb)
is impossible there — only a firmware change can help.

**MCU [C]:** Atmel AVR32 UC3A3/UC3A4 (`AT32UC3A4`, read off the PCB by a forum user and matching
our own decode). Big-endian. Flash base `0x80000000`; **file offset 0 == flash `0x80000000`**.
Internal SRAM at `0x00000000`, 64 KB (stack top `0x10000`). Firmware is plaintext, built on
Atmel's ASF (ASF USB device stack, `startup_uc3.S` reset path identified).

**Dual bank [C]:** `ONEv2_USB_Audio_Image0.bin` (98488 bytes) is linked for bank 0 at
`0x80004000`; `ONEv2_USB_Audio_Image1.bin` (229560 bytes) for bank 1 at `0x80024000`. Every
difference between the two bodies is a `+0x20000` relocation of a BE32 address in
`[0x80004000, 0x80024000)`. **Analyse Image0.** The bootloader occupies `0x0..0x4000` and is NOT
present in these files.

**Already finished — do not redo:**

- **The full vendor control protocol** over EP0. `bmRequestType 0x40` write / `0xC0` read,
  recipient = device. Key requests: `0x28` firmware version, `0x29` 6-byte hardware/knob state
  poll, `0x34` mic preamp gain (signed dB, **single register, no index**), `0x36` mic input type
  `{0=Internal, 1=External, 2=External+48V}`, `0x3E` instrument gain, `0x48` encoder-select,
  `0x53` output route, `0x33` output attenuation, `0x35` output mute.
- **The flash/update protocol**, and a working Windows flasher built on it. The ONE does **not**
  use DFU mode: flashing is vendor request `0xA9` against the running device, sub-command in
  `wValue`, index in `wIndex`, all integers big-endian. 512-byte pages as
  `SetFlashAddress → 8× WriteChunk(64B) → CommitFlashPage → 8× ReadChunk → compare`. Vendor
  `0xA7` = soft reset. A full bank now flashes in **11 seconds** with page-by-page read-back
  verification, so iterating firmware patches is cheap.
- **The descriptor work is COMPLETE.** Four rounds of patching made the configuration descriptor
  acceptable to Windows 11's inbox `usbaudio2.sys`. Event ID 34 ("a USB descriptor … is not
  compliant with the specification, or is not supported by the driver") has stopped appearing.
  Do not propose descriptor changes unless something below forces one.
- **The input-source control path.** `FUN_8000AA30(type, mode)` is the mic input setter (writes
  state variable `0x255C`, 0/1/2, and reconfigures the audio path). `FUN_8000A248` is the
  matching getter (serves vendor `0x36`). `FUN_8000A250` drives physical routing via
  `FUN_8000E360(reg, val)` (GPIO/codec helper, ~120 xrefs): `0x18`=PA10 / `0x19`=PA07 internal
  mic, `0x0D`=PB20 / `0x0E`=PB22 48 V phantom.
- **Peripheral map [C]** (addresses are built with `mov` of a negative immediate, not literals,
  which is why address scanning fails): WDT `0xFFFF0D30`, GPIO `0xFFFF1000`, USBB `0xFFFE0000`,
  INTC `0xFFFF0800`, PM `0xFFFF0C00`, RTC `0xFFFF0D00`, SPI1 (OLED) `0xFFFF2800`, TWIM0 (codec
  I²C) `0xFFFF2C00`, SSC (I²S) `0xFFFF3400`, TC0 `0xFFFF3800`, ADCIFA `0xFFFF3C00`.
- **`main()` is `FUN_80010C88`** [C, two independent ways: the device's own
  `GetAddressOfMain` vendor call returns `0x80010C88`, and that is the function that arms the
  watchdog]. The hardware WDT is armed once there: `0x80010CD6` writes key `0x55001301`,
  `0x80010CEC` writes `0xAA001301`; CTRL `0x1301` → prescaler 19 → ≈9.11 s.

**Known Ghidra AVR32 issues** (upstream PR #8907): `ST.B` displacement scaled wrongly, `CPC`
carry handling, and `MOV pc, …` not treated as a branch. Language id `avr32:BE:32:default`,
image base `0x80000000`. `pypcode` uses the same SLEIGH decoder and disassembles this image at
~99.8 %.

---

## 2. The context: why the next piece is needed

With the descriptor now accepted, Windows' class driver proceeds to the next stage and fails
there. The exact new symptom:

- `usbaudio2` logs **Event ID 38, "A control request sent to device … has failed"**, repeatedly.
- A UAC2 class control request sent directly to the device over EP0 returns
  **`LIBUSB_ERROR_PIPE`, i.e. the device STALLs it** [C, measured on hardware].
- Statically, the interface-recipient request handler **`FUN_80008432` handles only
  `SET_INTERFACE` (`0x0B`)**; there is no class-request handling at all [C, decompiled].

So **the firmware implements no USB Audio Class 2.0 control requests.** That single gap blocks
both goals at once:

- **Windows driverless:** `usbaudio2` must read the clock's sampling frequency (`GET CUR`,
  `GET RANGE`) and clock validity before it will start a stream.
- **iPad (the platform with no fallback):** iPadOS already accepts this descriptor and plays
  audio, but inputs do not register, because the standard **Selector Unit 15** cannot be driven —
  the only way to change input source today is the vendor request `0x36`, which iOS cannot send
  (no user-space raw USB, External Accessory is MFi-license-only).

The current live descriptor topology, for reference (328 bytes, read back off the device):

```
INPUT_TERMINAL 2  (USB stream, 2 ch, L/R) -> FEATURE_UNIT 4  (bLength 18) -> OUTPUT_TERMINAL 3
INPUT_TERMINAL 9  (internal mic + instrument, 2 ch) -\
INPUT_TERMINAL 11 (external mic + instrument, 2 ch) --> SELECTOR_UNIT 15 (pins 9,11,13)
INPUT_TERMINAL 13 (external 48V + instrument, 2 ch) -/        |
                                                             v
                                       FEATURE_UNIT 10 (bLength 18) -> OUTPUT_TERMINAL 8
CLOCK_SOURCE 1, bmAttributes 0x03 (internal programmable), bmControls 0x07
iso OUT ep 0x01 Adaptive, iso IN ep 0x82 Asynchronous, both wMaxPacket 128, bInterval 1
```

The intended patch, for which we need your findings:

| class request | should call |
|---|---|
| CLOCK_SOURCE 1, `CS_SAM_FREQ_CONTROL` `GET CUR` / `GET RANGE` | the sample-rate getter (`FUN_8000A1DC`?) |
| CLOCK_SOURCE 1, `CS_CLOCK_VALID_CONTROL` `GET CUR` | constant 1 |
| SELECTOR_UNIT 15 `GET CUR` | `FUN_8000A248` (+1, selector pins are 1-based) |
| SELECTOR_UNIT 15 `SET CUR` | `FUN_8000AA30(value - 1, 3)` |

New code will be placed in free flash: `ONEv2_USB_Audio_Image0.bin` ends at file `0x180B8` while
bank 0's app region runs to `0x20000`, leaving **32584 bytes** that our flasher can write.

---

## 3. What to find — the deliverable

**Map the EP0 control-request pipeline precisely enough to insert a new handler.** Concretely,
answer each of these, with addresses and with the decompiled/disassembled evidence:

1. **Dispatch chain.** Trace SETUP packet arrival to per-request handling. Known starting points
   [C]: EP0 SETUP ISR `FUN_80005C88`; master request handler `FUN_80008170` (also serves
   `GET_DESCRIPTOR`); vendor dispatcher `FUN_800093D4` (193-entry jump table at `0x80008CD4`,
   index = `bRequest - 0x10`); SET-side table at `0x80008A2C`; interface-recipient handler
   `FUN_80008432`. Fill in the gaps and draw the actual control flow.

2. **Where `bmRequestType` is decoded.** Identify the exact instruction(s) that test the type
   field (bits 6:5 — standard 0 / class 1 / vendor 2) and the recipient field (bits 4:0 — device
   0 / interface 1 / endpoint 2). **This is the hook point**: a class+interface request must reach
   our new code. Give the address, the surrounding bytes, and what currently happens to a
   class+interface request (which path leads to the STALL).

3. **The ASF `udd_g_ctrlreq` structure in this build.** ASF's `udd_ctrl_request_t` holds
   `req` (the 8-byte setup packet), `payload` (pointer), `payload_size`, `callback`,
   `over_under_run`. Find its RAM address and the offset of each field. Clues: the setup packet is
   read as `setup[1] == bRequest`; an EP0 OUT data stage is buffered at RAM `0x2454`; the
   configuration-descriptor emit path in `FUN_80008170` (the `bVar14 == 2` branch) sends from a
   per-speed pointer held in `_DAT_000003B0` / `_DAT_000003BC` and takes the length from the
   descriptor's own `wTotalLength` field. Determine whether those two are the ctrlreq payload
   fields or something separate.

4. **The success/STALL convention.** How does a handler tell the stack "I handled it" vs "STALL"?
   (ASF convention is a `bool` return from `udi_api.setup()`.) Name the register, the values, and
   the code that actually issues the STALL.

5. **How an IN payload is returned.** Is there a helper (ASF-style `udd_set_setup_payload(ptr,
   size)`)? If so give its address and signature. If the handler just writes the ctrlreq fields,
   say exactly which writes are required, in what order.

6. **How an OUT data stage is received** (needed for `SET CUR`): how `FUN_800093AC` arms EP0 OUT
   into buffer `0x2454` and how completion reaches `FUN_80009088`. We want the same mechanism for
   a class `SET CUR`.

7. **Signatures and calling convention** of the functions we intend to call: `FUN_8000AA30`,
   `FUN_8000A248`, `FUN_8000A1DC`, and whatever turns out to be the sample-rate getter. State the
   AVR32 GCC convention this build actually uses (argument registers, return register,
   callee-saved set, how `LR`/`SP` are handled) — verified from real prologues/epilogues, not
   assumed. Known markers: GCC prologue `EBCD4080`, epilogue `E3CD8080`.

8. **Supported sample rates.** `GET RANGE` must report them. Find the rate table or the clock
   configuration code (SSC/PM/codec setup) and list what the hardware actually supports. If only
   one rate is live at a time, say how the current rate is stored and read.

9. **Hook feasibility.** Propose a concrete insertion: which bytes to overwrite with a branch to
   free flash, the exact original bytes displaced, and how the new code preserves the original
   behaviour for requests it does not handle. Note that AVR32 branch range and alignment
   constraints matter — state them. Flag anything position-dependent that would differ in bank 1
   (`+0x20000`).

10. **Free-flash sanity.** Confirm whether `0x180B8..0x20000` is genuinely unused by the running
    image (not a data region reached by some pointer, not used by the bootloader for anything),
    and whether the linker script or any CRC covers it. Context: the updater, after writing a
    bank, reads a **device-computed "user page CRC"** (`0xA9` sub-command 4) and writes it back
    (sub-command 5) before setting the active image — find out what that CRC covers, because it
    determines whether appending code is safe.

**If you have budget after that:** draft the handler in AVR32 assembly *and* emit the machine-code
bytes, then verify by disassembling your own bytes (pypcode or Ghidra) and confirming they read
back as intended. We have no AVR32 assembler, so a hand-verified byte sequence is directly
useful. Keep it minimal: the four class requests in the table above, plus a clean fall-through.

**Also worth flagging if you see it:** the encoder handler is `FUN_8000CB40` (GPIO edge ISR
`0x8000D5E8+` → ring buffer `0x271C`, 9-state vtable `0x8000C370` → selection `0x2648`), and
`FUN_8000CAF0` looks like an input-type cycler. A later goal is a knob gesture (double/triple
click, hold) that calls `FUN_8000AA30` directly. Note anything that makes that easier, but do not
spend budget on it now.

---

## 4. Practical notes

- Analyse `ONEv2_USB_Audio_Image0.bin` at base `0x80000000` (file offset 0 = that address).
- Do not propose changes to the bootloader region `0x0..0x4000` — it is not in the file and is the
  only known recovery path.
- Two physical units exist; one is kept untouched as a spare, and both banks are independently
  flashable, so a bad experimental image is recoverable. Still, an image that fails to enumerate
  cannot be reached by our flasher (it needs the running app to answer `0xA9`), so changes must be
  conservative about boot and USB bring-up paths.
- Output as markdown with an addresses table. Separate **[C]** from **[H]** everywhere. If a
  question cannot be answered from the image, say so plainly rather than filling the gap.
