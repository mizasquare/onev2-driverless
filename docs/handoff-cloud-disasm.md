# Handoff — Apogee ONE v2 firmware: whole-program disassembly & architecture reconstruction

Paste this whole document into the cloud session, and attach the firmware file `ONEv2_USB_Audio_Image0.bin` (also attach `ONEv2_USB_Audio_Image1.bin` if you want the bank-1 twin). This is interoperability research on firmware the device owner legitimately possesses. STATIC analysis only — never execute anything. The owner's device is not present; do not propose flashing.

---

## 0. Your task

Do a **whole-program disassembly and architecture reconstruction** of this AVR32 firmware to produce a **big-picture map** we can reference. We have already reverse-engineered the input-control path, the vendor protocol, and key facts (section "KNOWN SIGNATURES" below) — **build on it, don't redo it.** Deliver:

1. **Function inventory** — every function (entry address), with an inferred name/role where possible, grouped by subsystem.
2. **Call graph** for the control paths (USB setup → dispatchers → setters → hardware), rendered as text/edges.
3. **Subsystem map**: USB device core (ASF UDC/UDI), UAC2 audio (streams, clock, feature/selector units), vendor control protocol, iAP (Apple accessory) stack, encoder/button + OLED/UI, power/clock, and the **self-disconnect watchdog**.
4. **Targeted answers** (these drive our project — highest value):
   - **R2 — the watchdog:** locate the timer/ISR that makes the device electrically detach/re-enumerate after ~9 s of no EP0 control traffic. Parse the exception/interrupt vector table at EVBA = 0x80016C00; find the periodic timer handler and the counter + threshold + the detach call. Report exact addresses and the condition.
   - **R3 — selector wiring:** does ANY standard UAC2 class-request handler (SET_CUR, bmRequestType 0x21, bRequest 0x01, to AudioControl interface, selector unit id 15) reach the input setter FUN_8000aa30 (0x8000aa30) OR write the staging var at RAM 0x3c? We found only two callers of FUN_8000aa30 (the vendor-0x36 path and the staged-apply FUN_800072c4). If there is NO standard-UAC2 path, say so explicitly. (This decides whether input switching is class-compliant today.)
   - **R4 — capture vs iAP:** does opening the USB capture (record) stream depend on the iAP session or vendor init? Trace the AudioStreaming interface-2 / alt-setting handling and whether a flag set only by iAP/vendor gates capture.
   - **R5 — encoder handler:** find the rotary-encoder + push-button event handler (the code that reads the knob and writes the "encoder select" state at RAM 0x2648, read by FUN_8000c484). This is where we'd add a gesture.
   - **Peripherals:** recover peripheral base addresses (AVR32 UC3 builds them via mov+orh / a base pointer, not plain 32-bit literals). Identify WDT, Timer/Counter (TC), USBB, GPIO, SSC/I2S, TWI/SPI bases, and map which functions touch each. Decode FUN_8000e360 (the 120-xref GPIO/codec write helper) — are its "reg" args GPIO pins or codec registers?

Report exact addresses for everything. Separate **confirmed-by-disassembly** from **inference**. Where you rename a function, give the evidence.

---

## 1. Toolchain (works in a cloud session, no admin, no large download)

AVR32 is big-endian; flash base = 0x80000000; the image is raw (no header). Use pypcode (Ghidra's decoder, pure-python wheel):

```bash
pip install pypcode
python -m pypcode -l | grep -i avr32      # -> avr32:BE:32:default
```

Minimal disassembler (linear sweep, resolves LDDPC literal targets):

```python
import struct, pypcode
BASE = 0x80000000
img = open("ONEv2_USB_Audio_Image0.bin","rb").read()   # file offset 0 == 0x80000000
ctx = pypcode.Context("avr32:BE:32:default")
def dis(start, end):
    pc = start
    while pc < end:
        tx = ctx.disassemble(img[pc-BASE:min(end,pc+32)-BASE], base_address=pc, max_instructions=1)
        ins = tx.instructions[0]; n = ins.length or 2
        print("0x%08X: %-10s %s" % (pc, ins.mnem, ins.body)); pc += n
dis(0x80004000, 0x80004040)
```

If Ghidra is available, use it headless for function detection + decompiler: processor `avr32:BE:32:default`, BinaryLoader, `-loader-baseAddr 0x80000000`. (Known Ghidra AVR32 spec bugs: ST.B displacement x4 wrong, CPC carry, `MOV pc,rX` not treated as branch — PR #8907.)

**Verification anchors** (if these don't decode as shown, your setup is wrong):
- 0x80000000: `BR 0x80004000` (reset trampoline)
- 0x80004000: `SUB PC, PC, -0x2950` → 0x80006950 (program_start → _stext)
- 0x80006950: `MOV SP, 0x10000` / `MTSR EVBA, R0` / .data+.bss loops (ASF startup_uc3.S _stext)

---

## 2. KNOWN SIGNATURES (established; build on these)

### MCU / memory
- **Atmel AVR32 UC3A3/UC3A4** (AVR32-A, big-endian). Confirmed: pypcode/Ghidra decode cleanly at base 0x80000000; AVR32-GCC prologue/epilogue present, ARM/Thumb patterns absent; stack top 0x10000 = 64 KB internal SRAM.
- File offset 0 == flash **0x80000000**.
- **0x80000000–0x80003FFF** = Apogee bootloader/DFU region (NOT present in the update image; first word is a BR trampoline to the app).
- **0x80004000** = bank0 application entry (program_start → _stext 0x80006950). **0x80024000** = bank1 (the second image, same code relocated +0x20000).
- **EVBA (exception vector base) = 0x80016C00.**
- Code ≈ 0x80004000–0x80016C00; strings/descriptor tables 0x80016C00+.
- RAM/SRAM: stack top 0x10000 (64 KB); globals in low RAM (0x0000xxxx) and ~0x2xxx.
- Images are **dual-bank**: Image0 (96 KB, bank0 @0x80004000), Image1 (224 KB, bank1 @0x80024000); the 662 byte diffs between them are ALL `+0x20000` relocations of absolute addresses. Plaintext (no encryption); trailing 4 bytes 0x00000A94 identical in both (not a content checksum).

### USB descriptors (on-wire, from the real device)
- UAC2 composite; VID 0x0C60 PID 0x0017; product "ONEv2"; bcdDevice 0x0105; enumerates high-speed.
- AudioControl IF0: clock source id1; playback IT2 → FU4 (mute+vol) → OT3 (Speaker); **capture: three Microphone input terminals 9/11/13 → FU10/12/14 (volume READ-ONLY) → SELECTOR UNIT id15 (3 inputs, control r/w) → OT8 (USB-IN).**
- AudioStreaming IF1 (OUT) and IF2 (IN), 24-bit in 32-bit slot, synchronous iso.
- **Vendor IF3**: class 0xFF / subclass 0xF0 / proto 0; bulk OUT 0x04, bulk IN 0x85, interrupt IN 0x86 (Apple iAP accessory channel).
- **Descriptor defects (why Windows inbox usbaudio2 rejects, Code 10 / 0xC0440022 / Event 34):** (a) CLOCK_SOURCE id1 declared twice; (b) the audio IAD count spans vendor IF3; (c) FU bLength is 10, spec wants 18 for 2-ch; (d) AC header wTotalLength 174 vs real 167.
- In-firmware descriptor tables (plaintext): device desc @0x800175F4, config copy A @0x80017614, config copy B @0x80017768 (identical). USB string descriptors: index 0x11 "iAP Interface", 0x12 "Internal Mic + Instrument", 0x13 "External Mic + Instrument", 0x14 "External 48V + Instrument" (= iTerminal of terminals 9/11/13). String-descriptor handler is FUN_80008170 (GET_DESCRIPTOR, type 3, switch on wValue low byte).

### Vendor control protocol (EP0; bmRequestType 0x40 write / 0xC0 read; wValue=0; wIndex=0; 1 data byte unless noted)
| bReq | meaning | notes |
|---|---|---|
| 0x14 | meter data | read, 16 bytes |
| 0x1f / 0x20 | meter peak / over hold | |
| 0x26 | identify (LED) | |
| 0x27 | clear meters | |
| 0x28 | firmware version / hardware UID | read, 3 bytes |
| **0x29** | **GetHardwareChanges** | read, 6 bytes — **this is the "keepalive" the host polls; a pure state read** |
| 0x31 | unknown (read 4, used in init) | |
| 0x33 | output attenuation | |
| 0x34 | mic preamp gain | signed byte |
| 0x35 | output mute | |
| **0x36** | **mic input TYPE** | **0=Internal, 1=External, 2=External+48V** |
| 0x3e | instrument input gain | signed byte |
| 0x3f | session token | |
| 0x44 | input grouping | |
| **0x48** | **encoder-select state** | read |
| 0x4c–0x4f | mixer fader/pan/solo/mute | wIndex = channel |
| 0x52 | suspend event / device prefix | |
| 0x53 | output route (source) | |
| 0xb6 | output reference level | wIndex = channel |
| 0x10 | SET-only, writes [0x00] in init | stream/clock enable? (unconfirmed) |

Host init sequence (from the Linux project, over EP0): reads (0x29,6)(0x31,4)(0x29,6)(0x1f,1)(0x20,1)(0x28,3)(0x36,1); write 0x34←[0x17]; reads (0x44,1)(0x3e,1)(0x33,1)(0x35,1)(0x53,1); write 0x10←[0x00]. Keepalive: read (0x29,6) every ~4 s or the device self-disconnects at ~9 s.

### Key functions (Ghidra default names, base 0x80000000) — CONFIRMED by decompilation
| addr | role |
|---|---|
| FUN_800093d4 | **vendor request dispatcher** — `switch(setup[1]=bRequest)`; GET vs SET by bmRequestType bit7 |
| FUN_800093ac | SET path: arms EP0-OUT data stage into buffer 0x2454, completion → FUN_80009088 |
| FUN_80009088 | **SET data-stage dispatcher** — `switch(bRequest)`; `case 0x36: FUN_8000aa30(*data, 3)` |
| **FUN_8000aa30**(type,mode) | **THE mic-input-source setter** — writes state var 0x255c (0/1/2), reconfigures audio path. Only 2 callers: FUN_80009088 (vendor 0x36) and FUN_800072c4 (staged apply) |
| FUN_800072c4 | staged-settings apply (dirty flag 0x11d2; input type from RAM 0x3c minus 1 → FUN_8000aa30); called by FUN_80010c88 |
| FUN_8000a248 | input-type getter (returns 0x255c) = 0x36 GET |
| FUN_8000a250 | physical routing: by 0x255c calls FUN_8000e360(reg,val): 0x18/0x19 = internal mic path, 0xd/0xe = 48V phantom |
| FUN_8000e360 | GPIO/codec register write helper (120 xrefs) — decode its reg map |
| FUN_8000a658 | boot / factory-reset defaults (0x255c=0, gain 0x30, sample rate 48000, …) |
| FUN_80008170 | standard request handler (GET_DESCRIPTOR; string idx 0x12/13/14 = input names) |
| FUN_8000f8fc | **iAP1 session tick** — start byte 0x55, lingo 0x38, checksum -(sum); retransmit 500 ticks ×10, session reload 10000 |
| FUN_8000f620 | iAP lingo parser (lingo 0x12/0x38/0x3a; string "iOS device not supported by Quartet" → shared ONE/Duet/Quartet codebase) |
| FUN_8000b6d0 | poll loop; sets the hardware-changes bitfield 0x2538 |
| FUN_8000a1d0 | reads+clears change flag 0x2538 (called in the 0x29 path) |
| FUN_8000c484 | returns current selection RAM 0x2648 (used by 0x29 and by 0x48 encoder-select) |

### State variables (RAM)
- **0x255c** = current mic input type (0 Int / 1 Ext / 2 Ext48V)
- 0x2538 = hardware-changes bitfield
- 0x2648 = current "selection" (encoder-select state)
- 0x3c = staged input type (1-based) for FUN_800072c4; 0x11d2 = staged-settings dirty flag
- 0x25ac = sample rate; 0x2560 = gain; 0x257c = grouping; 0x2454 = vendor-SET receive buffer

### Watchdog & iAP (context)
- **Watchdog:** device electrically disconnects + re-enumerates after ~9 s with no EP0 control request. Reset by servicing ANY EP0 request (the 0x29 handler itself has NO watchdog-pet code — it just reads state). Fed incidentally by macOS CoreAudio traffic; starves on idle bare Linux. **Timer/ISR not yet located — this is R2.**
- **iAP:** firmware runs an **iAP1** accessory session (0x55 framing) over vendor IF3; it's an MFi accessory. On USB-C iOS the iAP control path is gone, so input doesn't register (output still works). Relevant to R3/R4.

### Our project goals (for context on what matters)
- **P1: make the device fully USB-class-compliant** (works with no vendor driver/app on Windows + Mac + iPad) → needs R1 (fix descriptor defects — data patch, tables at 0x17614/0x17768/0x175F4), R2 (remove watchdog), R3 (wire standard selector to the setter), R4 (capture without iAP).
- **P2: encoder gesture → input switch** → R5 (encoder handler → FUN_8000aa30).

---

## 3. What to return
A single architecture document: function inventory + subsystem map + call graph edges for the control paths + the EVBA vector table + explicit located-or-not answers for R2/R3/R4/R5 with addresses, clearly tagging confirmed vs inferred. This becomes our master map; we'll do the actual patch design locally afterward.
