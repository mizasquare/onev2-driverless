# Handoff: disassemble the ONEv2 bootloader and find how to enter its DFU mode

One focused job. Please mark every statement you produce as **[C] confirmed** (you read it in the
bytes or in an authoritative doc — say which) or **[H] hypothesis**. An earlier round of this
project was set back twice by confident-sounding inferences that turned out wrong, including one
proposed code patch that would have bricked a flash bank, so labelling matters more than speed.
If a question cannot be answered from the binary, say so plainly instead of filling the gap.

---

## 1. The artifact

`ONEv2_bootloader_0x0-0x4000.bin` — 16,384 bytes,
sha256 `a6710b27d40375607fe333436ab6cab061427c973680485e96fdc50e9e1a6e68`.

- **Architecture: AVR32 (Atmel AVR32 UC3), big-endian.** Ghidra language id `avr32:BE:32:default`.
- **Load it at base `0x80000000`; file offset 0 == flash address `0x80000000`.**
- ~8,766 bytes of real content; the remaining 7,618 bytes are erased `0xFF`.
- This was read off a live device with our own flasher (vendor request `0xA9` read path). It is the
  real on-chip bootloader. It is **not** in any Apogee update file — the update files' first
  `0x4000` bytes are unrelated padding plus a `BR{al} 0x80004000` trampoline, and match this dump
  in only 1166 of 16384 bytes.

### Already established about it [C]

It is **Atmel's stock UC3 USB DFU bootloader**, not an Apogee creation:

| field | value | where |
|---|---|---|
| product string | `UC3A3 DFU 1.0.3` (UTF-16LE) | `0x1cb2` |
| manufacturer string | `ATMEL` | `0x1d20` |
| DEVICE descriptor | `12 01 0002 00 00 00 40 EB03 F12F 0010 01 02 00 01` → **VID `0x03EB`, PID `0x2FF1`**, bcdDevice `0x1000` | `0x1d0c` |
| CONFIGURATION descriptor | 27 bytes, 1 interface, self-powered, 100 mA | `0x1cf0` |
| INTERFACE descriptor | class `0xFE` / subclass `0x01` / protocol `0x02` = **DFU mode** | `0x1cf9` |
| DFU functional descriptor | `09 21 0F 0000 FFFF 0101` → bmAttributes `0x0F` (willDetach, manifestationTolerant, canUpload, canDnload), wTransferSize `0xFFFF`, **DFU 1.1** | `0x1d02` |

### Chip and memory facts [C]

- **Flash is 256 KB (`0x0..0x40000`) and the address decode ignores bit 18**: reading `x` and
  `x + 0x40000` returns byte-identical data (verified on five address pairs). Keep that in mind
  before concluding anything about addresses at or above `0x80040000`.
- Layout in use by the application firmware: bootloader `0x0..0x4000`; application **bank 0**
  `0x4000..0x20000`; a 16 KB gap `0x20000..0x24000` that is erased and belongs to neither bank;
  application **bank 1** `0x24000..0x40000`. Banks are independently flashable and the running
  application reports which is active.
- Internal SRAM is at `0x00000000`, 64 KB (the application's startup sets SP to `0x10000`).
- Peripheral bases used by the application, for reference: FLASHC is not yet identified, but
  WDT `0xFFFF0D30`, GPIO `0xFFFF1000`, USBB `0xFFFE0000`, INTC `0xFFFF0800`, PM `0xFFFF0C00`.
  The UC3 **user page** is conventionally at `0x80800000` — treat that as **[H]** until you
  confirm it from this binary's own accesses.
- An earlier analysis of the *application* claimed the application's user-page CRC is stored at
  `0x808001F4` (bank 0) / `0x808001F8` (bank 1). That is **[H]**, from a different binary; please
  check whether this bootloader reads anything at those addresses.

### AVR32 encoding facts already derived — do not re-derive [C]

From the AVR32 Architecture Document (32000D–04/2011) cross-checked against real instructions:

- `BR{cond4} disp21` **Format II**: bits 31..29 = `111`, bits 28..25 = `disp21[20:17]`,
  bits 24..21 = `0100`, bit 20 = `disp21[16]`, bits 19..16 = `cond4`, bits 15..0 = `disp21[15:0]`;
  `PC ← PC + (SE(disp21) << 1)`, range ±1 MB. So a first halfword of `e08X` is a branch with
  condition `X` (`al` = `0xF`) and all high displacement bits zero.
- `e0A0 <imm16>` is **RCALL**, not a branch (verified: `0x800063fe e0a00eb9` → `0x80008170`).
- Several 4-byte forms share the shape `e0 <op> <reg> <imm16>`: `MOV Rd,imm16` (`e067 1bdc` =
  `MOV R7,0x1bdc`), `CP.W Rd,imm16` (`e048 0020`), `ANDL` (`e218 0060`).
- GCC ABI in the sibling application binary: args R12, R11, R10, R9; return value R12; callee-saved
  R0–R7 and LR, pushed with `STM --SP,{...,LR}` (`ebcd40xx`) and popped with `LDM SP++,{...,PC}`
  (`e3cd80xx`); SP=R13, LR=R14, PC=R15. `RET Rs` (`5efc` = `ret r12`) moves Rs→R12, sets Z/N from
  it, and returns to LR.

### Tooling warning

Ghidra's AVR32 SLEIGH spec has open bugs (upstream PR #8907: `ST.B` displacement scaled wrongly,
`CPC` carry handling, `MOV pc,…` not treated as a branch). We also measured that pypcode (same
spec) finds **zero** `BR{al}` in a 90 KB AVR32 image, renders every 4-byte branch as
`ADD R0,R0,R0`, and decodes the two distinct loads `703c` and `70bc` identically as
`LD.W R0,R8[0x0]` though they must differ (they address `0x255c` and `0x25ac`). **Sanity-check any
load/store displacement and any branch target by hand against the raw bytes** rather than trusting
the decoder, and say when you have done so.

---

## 2. Context: why this matters

The owner wants a 2013-era Apogee ONE (USB `0c60:0017`) to keep working with no vendor driver and
no helper application, on Windows, macOS and an iPad. Four rounds of USB descriptor patches have
already made Windows' inbox `usbaudio2.sys` accept the device; the remaining blocker is that the
application firmware STALLs every USB Audio Class control request, so the next step is a small
**code** patch to the application. We have a Windows flasher that writes a bank in 11 seconds with
page-by-page verification.

The thing gating that code patch is recovery. Both our flasher and Apogee's updater reach the
device through vendor requests served by the **running application**, so an application image that
fails to boot or enumerate is unreachable by either — that has been the one unrecoverable outcome,
held off only by keeping one bank good and a second physical unit untouched.

This bootloader changes that, *if* we can enter it: it is an independent, standard DFU device that
`dfu-util` / `dfu-programmer` / Atmel `batchisp` can talk to with no Apogee software involved.

**So the question that decides whether we can safely patch code is: what makes this chip enter and
stay in the bootloader's DFU mode?**

---

## 3. What to find — the deliverable

### Primary, in priority order

1. **Every path into DFU mode.** Find the reset-time decision that chooses "stay in the bootloader"
   over "jump to the application", and document each condition with its address and the code that
   tests it. Stock Atmel UC3 bootloaders typically combine several; establish which of these this
   build actually uses, and the exact pin / address / value / polarity for each:
   - a **GPIO level sampled at reset** (which port and pin, active high or low, any debounce or
     hold time, and whether it is read via the GPIO base `0xFFFF1000`);
   - a **force-ISP / boot-key word in the UC3 user page** (which address, which magic value, and
     whether the bootloader clears it after acting on it);
   - a **word in SRAM or a retained register** set by the application before a soft reset — this is
     the most valuable answer for us, because it would be triggerable over USB from software;
   - **failing validation of the application area** (see 2).
   - any **timeout**: does it wait N ms for a USB host and then jump to the application, or stay
     forever?

2. **What it checks before jumping to the application, and where it jumps.** Does it validate a
   CRC, a signature, a magic word, or just the first instruction / a plausible stack pointer? Give
   the address of the check, what is compared against what, and the address it hands control to on
   success (we expect `0x80004000`, but confirm). If the check reads the user page, give the exact
   offsets. **If an invalid application reliably leaves the chip in DFU, say so explicitly — that
   is the single most useful sentence you can write.**

3. **A danger map: which DFU operations could permanently lock or brick this chip.** The Atmel
   AVR32 DFU/ISP protocol can address more than flash. Enumerate every memory unit / command this
   bootloader implements and flag the destructive ones — in particular anything that can set the
   **security bit**, program **BOOTPROT** or other fuses, disable JTAG, or erase the bootloader
   region itself. We need an explicit "never send these" list before anyone points a DFU tool at
   this device. Also state whether the bootloader can overwrite its own region.

4. **The command set it actually implements.** Standard DFU 1.1 requests (DETACH `0x00`,
   DNLOAD `0x01`, UPLOAD `0x02`, GETSTATUS `0x03`, CLRSTATUS `0x04`, GETSTATE `0x05`, ABORT `0x06`)
   plus Atmel's ISP command packets carried inside DNLOAD payloads (program start, read, change
   base address, select memory unit, blank check, CRC, start application, …). For each: the opcode
   bytes, the payload layout, and which memory units are selectable. Note the page/erase
   granularity it uses and the flash controller register block it drives.

### Secondary, only if budget remains

5. Does the bootloader touch the watchdog? The application arms a ~9.11 s hardware WDT
   (`0xFFFF0D30`, CTRL `0x1301`) in its `main()`. If the bootloader leaves a WDT running, a long
   DFU session could be interrupted — check whether it disables or pets it.
6. Anything that identifies the exact part. The product string says **UC3A3** while a forum reader
   reported `32UC3A4` from PCB photos; flash is measured at 256 KB, which fits `AT32UC3A3256` and
   `AT32UC3A4256` alike. If the binary pins it down (a chip-ID read, a part-specific register, a
   flash-size query), say how.
7. Whether the bootloader's USB stack would appear at `03EB:2FF1` on a bus with the application's
   `0c60:0017` identity gone, and whether it reports a serial number string (useful for telling two
   units apart).

### Deliverable format

Markdown, with an addresses table up front, then one section per numbered question. Include the
raw bytes for every instruction you build an argument on, so the reasoning can be re-checked
against the binary. Separate **[C]** from **[H]** throughout.

---

## 4. Scope limits

- **Static analysis only.** Do not propose running, flashing, or sending anything to hardware; the
  owner executes all device interaction, and a wrong DFU command here is the one thing that could
  permanently lock the part.
- **Do not propose modifying the bootloader.** It is the recovery path; it stays untouched.
- You do not need the application firmware for this task. If a question genuinely requires it, say
  which function you would need and why, and leave it open.
