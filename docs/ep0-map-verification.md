# Verification of the cloud session's EP0_PIPELINE_MAP

Everything below was re-checked locally against `ONEv2_USB_Audio_Image0.bin` (byte reads and
arithmetic on real instruction displacements) and, where noted, against the live device over our
own flasher. **[C]** = I confirmed it myself. **[X]** = I found it wrong. **[?]** = I could not
determine it with the tools available.

## Confirmed independently [C]

| claim | how I checked it |
|---|---|
| hook site `0x80008170` begins `ebcd40fc` = `STM --SP,{R2..R7,LR}` | byte read, exact match |
| next instruction `0x80008174` is `e0671bdc` = `MOV R7, 0x1bdc` | byte read — this *is* the ctrlreq base being loaded, so the `0x1bdc` claim stands |
| `bmRequestType` decode block at `0x8000818A` | bytes `0c98 e2180060 5f09 e0480020 5f0b` decode exactly as the map says (`MOV R8,R6` / `ANDL R8,0x60` / `SR{EQ} R9` / `CP.W R8,0x20` / `SR{EQ} R11`) |
| `FUN_8000A248` = leaf getter of RAM `0x255c` | `e0682550` = `MOV R8,0x2550`, then a `LD.W` at `+0xc`, then `5efc` = `RET R12`. `0x255c` is the mic-input-type variable we had already established independently |
| `FUN_8000A1DC` = leaf getter of RAM `0x25ac` | `e0682580` = `MOV R8,0x2580`, load at `+0x2c`, `RET R12` |
| the SETUP ISR calls the master handler from `0x800063fe` | `e0a00eb9`: `0x800063fe + 2*0x0eb9 = 0x80008170` exactly. This also proves `e0A0` = **RCALL**, not a branch |
| STALL path builds the USBB base | `0x800064f6` is `MOV R8, -0x20000` = `0xFFFE0000`; `UECON0SET` at `+0x1F0` follows |
| CRC routine literals | `0x8000d860 = 0x80024000`, `0x8000d864 = 0x80004000` — the two bank bases, as claimed |
| the free tail is erased | live device read: `0x1FF00` and `0x20000` are 256×`0xFF` |

## CORRECTION (same day): the hook encoding is RIGHT — I was wrong below

The section below concluded the hook bytes were wrong. That conclusion was itself wrong, and it is
kept here only so the reasoning error is visible. The AVR32 Architecture Document (32000D–04/2011,
`doc32000.pdf`, p.143-144) gives `BR{cond4} disp21` Format II as:

```
bits 31..29 = 111
bits 28..25 = disp21[20:17]
bits 24..21 = 0100            <- opcode
bit  20     = disp21[16]
bits 19..16 = cond4
bits 15..0  = disp21[15:0]
PC <- PC + (SE(disp21) << 1)          range +/- 1 MB
```

Checked against the firmware: `e085 00cf` has bits 19..16 = `0101` = 5 = `lt`; `e081 00f3` has
`0001` = `ne`. So the displacement is **21 bits**, with its high bits and sign in the *first*
halfword (bits 28..25 and bit 20) — fields that are zero in all 1154 long branches in this image
because every real displacement is positive and below `0x10000` halfwords. That is exactly why my
empirical test could not separate the cases: I tested two hypotheses and the truth was a third.

`e08f bf48` therefore means `disp21 = 0x0BF48`, sign bit clear, target `0x80020000`. **Correct.**
Backward displacements are equally fine, so a handler anywhere within +/-1 MB can branch back.

The lesson stands even though the verdict flipped: "best fit among the hypotheses I happened to
think of" is not proof. The authoritative encoding table settled it in one lookup.

The two *other* objections below do survive, and one of them is confirmed by measurement:

- **`0x80040000` is not a valid bank-1 target.** Flash is 256 KB and the address decode ignores
  bit 18: reading `(x)` and `(x + 0x40000)` returns byte-identical data for every pair tested
  (`0x0`/`0x40000`, `0x1000`/`0x41000`, `0x8000`/`0x48000`, `0x4000`/`0x44000`,
  `0x20000`/`0x60000`). So `0x80040000` **aliases to `0x80000000`, the reset vector**. Bank 1 needs
  its own displacement, not the same bytes.
- **The CRC relocation argument is moot for us** (our flasher re-stores the device-computed CRC).

And the free region is real: `0x20000`, `0x22000`, `0x23000`, `0x23f00` all read as all-`0xFF`,
with bank-1 code starting at `0x24000`. The earlier single read failure at `0x23f00` was
transient — the device drops its USB handle while usbaudio2 retries, and a retry on the dead
handle never recovers; the handle has to be re-acquired.

Note for future probing: `SetFlashAddress` aligns down to a 64-byte boundary, so an unaligned
probe address returns the containing chunk (this made an aligned-looking comparison at `0x17614`
appear to mismatch when it did not).

## The original, mistaken section [X — superseded by the correction above]

**The hook encoding `e08fbf48` and the hook target `0x80020000`.**

The 4-byte branch/call form in this firmware is `e0 <op> <cond/reg> <imm16>`, the same shape as
`MOV Rd,imm16` (`e067 1bdc`), `CP.W Rd,imm16` (`e048 0020`) and `ANDL` (`e218 0060`). The
displacement therefore occupies **16 bits**, in halfwords, relative to the instruction address.
I verified this on two instructions whose targets are independently known:

```
0x800081CA  e085 00cf   ->  0x800081CA + 2*0x0CF = 0x80008368   (cond 5)
0x800081D2  e081 00f3   ->  0x800081D2 + 2*0x0F3 = 0x800083B8   (cond 1)
0x800063FE  e0a0 0eb9   ->  0x800063FE + 2*0xEB9 = 0x80008170    (RCALL)
```

Reading all 1154 such instructions in the code region under "the 16-bit field is the whole
displacement" puts **1154/1154 targets inside the image, none unaligned**. The rival reading (bit
5 of the first halfword as a 17th/high bit) puts only 647/1154 inside. So the 16-bit field is the
whole displacement.

The jump the map proposes needs `(0x80020000 - 0x80008170)/2 = 0xBF48` halfwords, which **does not
fit a 16-bit signed field** (max `0x7FFF`). Under the best-fitting reading, `e08fbf48` is
`0xBF48 - 0x10000 = -16568` halfwords, i.e. a branch to **`0x80000000` — the reset vector**. The
`STM` prologue would also be gone, so every control request would reset the chip: a boot loop,
and the bank would be unreachable by our own flasher, which needs the running app to answer
`0xA9`.

Two further problems with the same proposal:

- **The bank-1 story cannot work.** The map says the identical bytes at `0x80028170` would reach
  "`0x80040000`, bank-1's CRC-immune region". Bank 1's app region *ends* at `0x40000`, so
  `0x80040000` is the first address past the end of flash.
- **`0x80023F00` is not readable on the live device** (the flash read command returned an I/O
  error, while `0x20000` read fine), so the "16 KB region at `0x20000..0x24000`" is at best
  partly accessible — the `0x80023FFF` write bound in the map is not something the device honours
  for reads.

**And the CRC argument the whole relocation rests on is moot for us.** Our flasher reproduces the
updater's sequence: after writing it reads the *device-computed* user-page CRC (`0xA9` sub-cmd 4)
and stores it back (sub-cmd 5) before setting the active image. Whatever we write, the stored CRC
matches it. So there is no reason to avoid the image's own free tail.

## Could not determine [?]

**How the top bit of the displacement field is treated.** Not one of the 1154 long
branches/calls in this firmware uses a field value `>= 0x8000`, so the image contains no evidence
either way. Any patch that needs a displacement at or above `0x8000` — including a *backward*
branch from a handler in the free tail back to `0x80008174`, which needs `0x805A` — is an
unverified gamble.

**Our disassembler is unreliable on exactly the instructions we need.** pypcode (same SLEIGH spec
as Ghidra, which has open AVR32 bugs) finds **zero** `BR{al}` in the whole image, renders every
long branch as `ADD R0,R0,R0`, and decodes the two distinct loads `703c` and `70bc` identically as
`LD.W R0,R8[0x0]` — though they must differ, since they produce `0x255c` and `0x25ac`. So it
cannot be used to check hand-written code.

## Consequence for the plan

Hand-assembling the handler is not safe with current tooling: the one load-bearing encoding in
the cloud's design is both unverifiable here and, on the best available reading, catastrophic, and
the return path needs the same unverifiable bit. **Get a real AVR32 assembler** (avr32 binutils /
the Microchip AVR32 GNU toolchain) before writing any code patch — it gives both a correct
assembler and `objdump` to verify the bytes.

If a handler is placed in the image's own free tail instead of `0x20000`, the *forward* hook
becomes unambiguous — e.g. a handler at `0x800180C0` needs `(0x180C0-0x8170)/2 = 0x7FA8 < 0x8000`,
so `e08f7fa8`, valid under every reading, and identical in both banks since hook and target both
relocate by `+0x20000`. The file simply has to be extended past its current `0x180B8` end, which
our flasher handles (it writes whatever pages the file contains inside the bank window). The
return to `0x80008174` should then be an absolute jump built from immediates rather than a long
backward branch.
