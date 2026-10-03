# Plan under review: a UAC2 class-control handler patched into the ONEv2 firmware

Self-contained brief. Nothing here should be taken on trust — the point of the review is to find
what is wrong, missing, or unjustified. Confidence tags: **[C]** verified from bytes/hardware/an
authoritative doc, **[H]** hypothesis.

## 1. The device and the goal

Apogee ONE 2nd generation, USB `0c60:0017`, a 2013-era 2-in/2-out audio interface (built-in mic,
external mic with 48 V phantom, instrument input, encoder knob, OLED). MCU: Atmel AVR32 UC3,
**big-endian**, 256 KB flash, 64 KB SRAM at `0x00000000`, firmware built on Atmel ASF. Owner wants
it working with **no vendor driver and no helper app** on Windows, macOS and iPad.

Four rounds of USB descriptor patches already made Windows 11's inbox `usbaudio2.sys` **accept the
descriptor** [C — `usbaudio2` Event ID 34 stopped, 0 in 15 min]. The remaining blocker is that the
firmware **STALLs every USB Audio Class control request** [C, three independent ways: the
interface-recipient handler `FUN_80008432` only handles `SET_INTERFACE`; Windows now logs Event ID
38 "a control request sent to device has failed" 30×/15 min; a class request sent directly over EP0
returns `LIBUSB_ERROR_PIPE` = STALL]. The same gap blocks the iPad, where playback already works but
inputs never register because the standard Selector Unit cannot be driven.

## 2. Established facts the plan rests on

### Flash / banks [C]
- Bootloader `0x0..0x4000`; app **bank 0** `0x4000..0x20000`; unused 16 KB gap `0x20000..0x24000`;
  app **bank 1** `0x24000..0x40000`. File offset 0 == flash `0x80000000`.
- `Image0.bin` (98488 B) is linked for bank 0, `Image1.bin` (229560 B) for bank 1; all differences
  are `+0x20000` relocations. Image0 ends at file `0x180B8`, so `0x180B8..0x20000` is erased.
- **Flash address decode ignores bit 18**: `read(x) == read(x+0x40000)` byte-identical on five
  tested pairs. So `0x80040000` aliases to `0x80000000`, the reset vector.
- We have our own Windows flasher (vendor request `0xA9`, no DFU needed): a bank writes in **11 s**
  with per-page read-back verification, then it reads the device-computed user-page CRC and stores
  it back before switching the active image. Writing and activating are separate commands.

### The request path [C]
- EP0 SETUP ISR fills an 8-byte setup packet and byte-swaps `wValue`/`wIndex`/`wLength` to
  big-endian, then `rcall 0x80008170` (the master request handler) and STALLs if it returns 0.
- `0x80008170` begins `ebcd40fc` = `STM --SP,{R2,R3,R4,R5,R6,R7,LR}`; the next instruction at
  `0x80008174` is `e0671bdc` = `MOV R7, 0x1bdc`.
- ASF `udd_g_ctrlreq` lives at **SRAM `0x1bdc`**: `+0x00` 8-byte setup packet, `+0x08` payload
  pointer (u32), `+0x0C` payload_size (**u16**), `+0x10` callback (u32), `+0x14` cleared at entry.
- Handler contract: return **R12 = 1 with Z clear** to claim a request; R12 = 0 / Z set means not
  handled, and the caller STALLs. `GET_DESCRIPTOR` works exactly this way — it writes the pointer
  and length into those fields and returns 1 — and the IN data-stage engine then streams
  `min(wLength, payload_size)` bytes **byte-for-byte, no swapping**, so a payload must already be
  in USB little-endian order.
- Useful existing leaves: `FUN_8000A248` = `mov r8,0x2550; ld.w r12,r8[0xc]; ret r12` → current mic
  input type from SRAM `0x255c` (0=internal, 1=external, 2=external+48V). `FUN_8000A1DC` →
  sample rate in **Hz** from SRAM `0x25ac`. `FUN_8000AA30(R12=type, R11=mode)` sets the input.
- Live descriptor topology: `CLOCK_SOURCE 1` (bmAttributes `0x03`, bmControls `0x07`);
  `SELECTOR_UNIT 15` with pins `[9,11,13]`; `FEATURE_UNIT 10` after the selector → `OUTPUT_TERMINAL 8`;
  `FEATURE_UNIT 4` on the playback path. Rates the hardware configures: 44100/48000/88200/96000 Hz.

### Recovery [C unless noted]
- The bootloader is **Atmel's stock UC3 USB DFU bootloader** (`03EB:2FF1`, DFU 1.1, product string
  `AT32UC3A3 DFU 1.0.3`), dumped off the live device.
- It enters DFU iff **RCAUSE shows a watchdog reset AND SRAM word `*(0x00000000)` == `0x4953504B`
  ("ISPK")**. On a non-WDT reset a stray key is cleared and the app is run. On DFU entry it disables
  the WDT.
- **There is no "bad app → DFU" fallback.** The launcher CRC-checks the preferred bank against the
  stored user-page CRC and, on mismatch, flips to the other bank and `ICALL`s it *unconditionally*.
  So a wrong-CRC image never runs (automatic A/B failover), but a valid-CRC yet broken image is
  launched anyway.
- The app arms a ~9.11 s hardware WDT and **never disarms it** [C: `0x55001301`/`0xAA001301` each
  appear exactly once, `0x..001300` and bare-key variants appear zero times]. A WDT service routine
  spans ~`0x80010FE0..0x80011078` and both pets (`st.w r8[0x4],r3` → WDT CLR) and re-arms.
- The app's startup initialises `.data` from RAM `0x08`..`0x0b88` and zeroes `.bss`
  `0x0b88`..`0x3610`. **RAM `0x00`..`0x07` is reserved and untouched**, and no observed app access
  targets `0x00` or `0x04`.
- A GPIO recovery pin may exist, configured in user-page word `0x808001FC` — **we cannot read it**:
  the `0xA9` read path returns all `0xFF` for the whole user page while the device's own CRC getter
  returns real stored values, so that path cannot address the user page. Treat the pin as absent.

### Tooling [C]
`resources/patch/avr32asm.py` — a minimal AVR32 assembler plus a separately written disassembler,
validated on 17 real instructions from this device's own firmware and bootloader (two properties
per instruction: our decoder reads the real bytes correctly, and our encoder's output decodes back
to the same mnemonic). It always emits the 4-byte branch form so instruction sizes are fixed.
Supported: `mov Rd,imm21`, `cp.w Rd,imm21`, `cp.w Rd,Rs`, `orh Rd,imm16`, `ld.w`, `st.w`, `st.h`,
`br{cond}`, `rcall`, `ret{cond} Rs`, `.word/.byte/.raw`. No AVR32 toolchain is obtainable for this
machine, and pypcode/Ghidra's AVR32 decoder is demonstrably wrong on branches and on `ld.w`
displacements, so this tool is the only verification path.

## 3. The proposed patch

### Placement
Handler goes in **each image's own erased tail** (`0x800180C0` in bank 0, `0x800380C0` in bank 1),
not the inter-bank gap. Hook site and handler both shift `+0x20000` between banks, so the
displacement — and therefore the patch bytes — are identical in both images. The image file is
extended past `0x180B8`; the flasher writes whatever pages the file holds inside the bank window.

### Hook
Replace the 4-byte `STM` at `0x80008170` with `br{al} <handler>` (same size). The handler re-executes
the displaced `STM` verbatim on the not-ours path, then branches to `0x80008174`.

### Handler, in the verified instruction set
```
handler:
  ; --- escape hatch, written once per request ---
  mov   r8, 0                 ; reserved SRAM word, outside .data/.bss
  mov   r9, 0x504b
  orh   r9, 0x4953            ; 0x4953504B "ISPK"
  st.w  r8[0x0], r9           ; any later watchdog reset now lands in DFU

  ; --- is this one of ours? ---
  mov   r8, 0x1bdc            ; udd_g_ctrlreq
  ld.w  r9, r8[0x0]           ; bmRequestType<<24 | bRequest<<16 | wValue  (wValue already BE)
  ld.w  r10, r8[0x4]          ; wIndex<<16 | wLength
  ; word0 identifies the request outright, so no masking or byte loads are needed:
  ;   0xA1010100 = class IN, CUR,   CS_SAM_FREQ      -> clock 1 (wIndex 0x0100) or selector (0x0F00)
  ;   0xA1020100 = class IN, RANGE, CS_SAM_FREQ      -> clock 1
  ;   0xA1010200 = class IN, CUR,   CS_CLOCK_VALID   -> clock 1
  ;   0x21010100 = class OUT, CUR,  SU_SELECTOR      -> selector 15 (phase 2)
  ; dispatch, then for each case:
  ;   build the little-endian response into a scratch buffer
  ;   st.w  r8[0x8], <buf>    ; ctrlreq.payload
  ;   st.h  r8[0xc], <len>    ; ctrlreq.payload_size (u16)
  ;   mov   r12, 1 ; ret{al} r12
not_ours:
  .raw  ebcd40fc              ; the displaced STM, re-executed
  br{al} 0x80008174           ; continue the original function
```
Phase 1 implements the three clock GETs plus `SELECTOR_UNIT 15` GET CUR (1 byte, **1-based** pin
index, so `FUN_8000A248()+1`). Phase 2 adds selector SET CUR via the OUT data stage
(`payload`=buffer, `payload_size`=`wLength`, `callback`=our routine, which reads the byte and calls
`FUN_8000AA30(value-1, 3)`).

Planned responses, all little-endian on the wire:
- `CS_SAM_FREQ` GET CUR → 4 bytes, current rate in Hz.
- `CS_SAM_FREQ` GET RANGE → `wNumSubRanges` then `{dMIN,dMAX,dRES}` per rate; intended set
  {48000, 88200, 96000} with `dRES`=0.
- `CS_CLOCK_VALID` GET CUR → 1 byte, `1`.
- `SELECTOR_UNIT 15` GET CUR → 1 byte, current input +1.

### Why the escape hatch
A patched image that boots but fails to enumerate is unreachable by every tool we have (our flasher
and Apogee's updater both need the running app to answer `0xA9`). Writing "ISPK" to the reserved
SRAM word means any watchdog reset lands in DFU instead of re-running the broken image.

### Risk ladder as planned
Flash the inactive bank, `verify` the whole bank against the file, only then `activate`. The other
bank keeps known-good firmware; a second physical unit is untouched. Never send DFU memory unit 2
(sets the permanent SECURITY bit) or unit 3 (GP fuses incl. BOOTPROT).

## 4. Known-open questions

1. Whether `cp.w Rd,Rs` (one witness) and `RCALL`'s high displacement bits (low 16 verified) are
   right. A wrong compare mis-dispatches; it should not brick.
2. What calls the WDT service routine and how often — i.e. the latency from hang to DFU.
3. Whether a legitimate watchdog reset during normal use would now drop the device into DFU, and
   whether that is acceptable.
4. Whether `usbaudio2` will demand more than these four requests before it starts a stream
   (feature-unit volume/mute are declared in the descriptor, `0x04` read-only on the mic FU and
   `0x0f` RW on the playback FU).
5. Whether the hook at function entry is the right place versus the point where a class request is
   actually rejected.
