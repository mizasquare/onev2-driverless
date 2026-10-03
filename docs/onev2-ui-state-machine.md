Verified: `FUN_8000C4A0`'s only two callers are at 0x8000C332 and 0x8000C382, both inside the battery/power routine — no vendor request drives the state-7 bitmask. State 7 is dead on a complete enumeration of both write paths.

---

# ONE v2 (0c60:0017) — front-panel state machine, and one patch for "long press cycles the mic source"

All work read-only against `firmware/ONEv2_USB_Audio_Image0.bin`. No `.bin` in `resources` was modified. Every byte quoted below was re-read from that file in this session with the corrected decoder (`avr32dis.py`, md5 `3dede06ebd055aa977da1df94c05fc28`, line 220 = `(L<<8)|H`); I did not take any address on trust from the traces.

**One correction to the task's own framing, up front, because the whole patch design turns on it:** the file loads at `0x80000000`, so file offset = address − `0x80000000`. The *application body* is linked at `0x80004000`, which is file `0x4000`.

---

## 1. The state machine as the code implements it

### The variables

| RAM | Width | Meaning | Confidence |
|---|---|---|---|
| `0x2648` | u32 | **the focus state**, 0..8. Index into the 9-entry `{handler, aux}` table at flash `0x8000C370` (8-byte stride) | [C] — `0x8000c484` = `e0682648 700c 5efc`; dispatch `ea080338` = `ld.w r8,r5[r8<<3]` + `5d18 icall`; 9 pairs hexdumped, 10th slot is `01010101` then the prologue `ebcd40c0` at `0x8000c3bc` |
| `0x264C` | u32 | state being left. **8 writers, zero readers anywhere in the image** — vestigial | [C] — my EA scan: stores at `c49a c6b8 c75a c794 c806 c840 c8b2 c8ec`, no loads |
| `0x2650` | u8 | blink-A enable = current output-mute value | [C] — set only by `FUN_8000C4E8` `0x8000c50a` |
| `0x2651` | u8 | blink-B enable (level-meter LEDs `0x20`/`0x1d`) | [C] |
| `0x2652` | u8 | Identify flag (vendor `0x26`) | [C] |
| `0x2654` / `0x2656` / `0x2658` | s16 | blink-A reload 50 / blink-B reload 25 / **long-press countdown reload 105** | [C] — `FUN_8000C3BC`: `ae68`(0xc)=50, `ae78`(0xe)=25, `ef580010`(0x10)=0x69 |
| `0x265A` / `0x265B` | u8 | blink-A / blink-B phase | [C] |
| `0x265C` | u8 | **long-press one-shot latch** | [C] — set `0x8000cbd8`, cleared `0x8000cc8a`, init 0 `0x8000c3da` |
| `0x2660` | u8 | state-7 LED bitmask | [C] |
| `0x255C` | u32 | **mic source**: 0 Internal / 1 External / 2 External+48V | [C] — `0x8000a248` = `e0682550 703c 5efc`, EA `0x2550+0xc` |
| `0x2550` b0 | u8 | **output mute** (what vendor `0x35` GETs/SETs) | [C] — `0x8000a208` = `e0682550 118c 5efc`; `0x35` GET at `0x80009aee` rcalls it, `0x35` SET at `0x8000927c` calls `FUN_8000AB84` which stores it at `0x8000aba2` |
| `0x257C` | u8 | **channel-grouping flag** — decides whether the focus ring includes the instrument stop | [C] — `0x8000a23c` = `e0682550 f13c002c 5efc` |
| `0x271C`/`0x271D`/`0x271E`/`0x2720` | u8,u8,u8,u32 | encoder up / encoder down / **any-edge pending** / button level (1=down, 2=up) | [C] — and `0x271E` is **any-edge**, not release-edge: the press arm at `0x8000d6ee` ends `cecb` → `0x8000d6ce`, the same `st.b r8[0x2],r9` the release arm uses |
| `0x1B94` | u32 | focus state parked across USB suspend | [C] — 5 accesses, all base `0x196c+0x228` |

### The engine

`FUN_8000CB40` (`0x8000CB40`..`0x8000CC96`) is the whole UI. Exactly one reference in the image: `0x80010ede feb0de31`. It runs once per main-loop pass, and the loop reloads `*0x3004 = 10` at `0x80010eb6` before calling it, so one pass = 10 RTC interrupts. **[C]**

It calls `FUN_8000D584` (`button_poll`) and dispatches on the result:

| poll result | meaning | what the tick does | at |
|---|---|---|---|
| 0 | nothing pending | `vtable[state](3)` — **TICK**, services the encoder | `0x8000cc50 rcall 0x8000c44c` |
| 2 | press completed (released) | `vtable[s](2)`, `vtable[s](1)`, `vtable[s'](0)` — EXIT / PRESS / ENTER | `0x8000cc90 rcall 0x8000c41c` |
| 3 | still held | decrement `0x2658`; at 0 and latch clear → **LONG PRESS** | `0x8000cbc8` |

Event codes to a handler: **0 = ENTER, 1 = PRESS, 2 = EXIT, 3 = TICK**. [C] — `FUN_8000C41C` re-reads `*0x2648` between its three `icall`s (`6c08` at `c42a`/`c432`/`c43c`), so the middle call is the one that writes the next state.

Two gates I verified myself and that matter to the patch:

- `0x8000cb4c cp.w r8,0x8 / c290 breq 0x8000cba0` — **state 8 returns before the button is even polled.** [C]
- `0x8000cba8 c2a3 brcs 0x8000cbfc` — **states 0 and 1 never reach the event logic.** State 0 then runs the EXIT/PRESS/ENTER triple *unconditionally, with no button press at all* (`0x8000cc00`..`0x8000cc1e`), so **state 0 self-advances to 6 on the very first tick**. State 1 (`brne 0x8000cb6c` at `0x8000cbfe`) does nothing. [C] — this is a refinement of the traces, which described state 0 as reacting to a press.
- Therefore the long-press block is reachable **only in states 2,3,4,5,6**. [C]

### Diagram

```
                          vendor 0x48 SET=2             vendor 0xA0 -> 8
                     ┌───────────────────────────┐   ┌────────────────────┐
                     v                           │   v                    │
   ┌──────────┐  first tick   ┌─────────────────────────┐            ┌─────────┐
   │ 0 boot   │──────────────>│  6  OUTPUT / headphone  │<───────────│ 8 ident.│
   │ (RAM=0)  │  auto, no     │  LED 0x22   knob: 0x2558│  0xA0 -> 6 │ all LED │
   └──────────┘  button       │  (output attenuation)   │            │ BUTTON  │
                              └─────────────────────────┘            │ DEAD    │
         ┌──────────────┐          │ PRESS: read 0x255C              └─────────┘
         │ 1  SUSPEND   │          v  type 0->3, 1->4, 2->5
         │ all LEDs off │   ┌───────────────────────────────────────┐
         │ BUTTON DEAD  │   │       M I C   F O C U S               │
         └──────────────┘   │  ┌─────┐    ┌─────┐    ┌─────┐        │
            ^        │      │  │  3  │    │  4  │    │  5  │        │
      USB   │        │ USB  │  │Int. │    │Ext. │    │Ext. │        │
      susp. │        │ res. │  │LED10│    │LED0f│    │+48V │        │
            │        v      │  │gain0│    │gain1│    │LED0f│        │
      (0x1B94 saves/         │  └─────┘    └─────┘    │+0x0e│        │
       restores the state)   │     ^          ^       │gain2│        │
                             │     └──────────┴───────┴─────┘        │
                             │   source changes ONLY via FUN_8000CAF0 │
                             │   (driven by the work queue, never by  │
                             │    the panel)  <-- the patch target    │
                             └───────────────────────────────────────┘
                                  │ PRESS
                 grouping flag 0x257C == 0  │  != 0
                      ┌───────────────┘     └──────────────┐
                      v                                    v
             ┌──────────────────┐                    back to state 6
             │ 2 INSTRUMENT hi-Z│──── PRESS ───────> state 6
             │ LED 0x11  gain3  │
             └──────────────────┘

   ┌─────────────────────────────────────────────────────────────────┐
   │ 7  host LED-bitmask override  —  UNREACHABLE IN THIS IMAGE      │
   │ 136 bytes of dead code at 0x8000C5D4..0x8000C65B                │
   └─────────────────────────────────────────────────────────────────┘

   LONG PRESS (held 105 passes), states 2..6 only:
        toggle output mute (RAM 0x2550 b0) + start speaker LED 0x22 blinking
        — the focus ring underneath is NOT touched
```

### Transition table

| # | From | Event | To | Where in flash | C/H |
|---|---|---|---|---|---|
| 1 | 0 | first tick (no button) | 6 | `0x8000cc00`–`0x8000cc1e` drives the triple; `0x8000c496 st.w r8[0x0],r9` (r9=6) | [C] |
| 2 | 6 | PRESS | 3 / 4 / 5 by `0x255C` | `0x8000c6a4 rcall 0x8000a248`; stores `0x8000c6b4`(3) `0x8000c6e0`(4) `0x8000c6f4`(5) | [C] |
| 3 | 6 | PRESS, type ≥ 3 | **6** (no change) | `0x8000c6e4 cp.w r12,0x2 / c040 breq`, else `0x8000c6e8`→`0x8000c6b6` writes only `0x264C` | [C] |
| 4 | 3/4/5 | PRESS, `0x257C`==0 | 2 | `0x8000c8a2`/`0x8000c7f6`/`0x8000c74a rcall 0x8000a23c`; stores `0x8000c8ae`/`0x8000c802`/`0x8000c756` (=2) | [C] |
| 5 | 3/4/5 | PRESS, `0x257C`!=0 | 6 | `brne` → `0x8000c8e2`/`0x8000c836`/`0x8000c78a`; stores `0x8000c8e8`/`0x8000c83c`/`0x8000c790` (=6) | [C] |
| 6 | 2 | PRESS | 6 | `0x8000c956 st.w r8[0x0],r9` (r9=6) — does **not** write `0x264C` | [C] |
| 7 | 3/4/5 | TICK | self; `FUN_8000AF40(0/1/2, delta)` → gain `0x2560+type` | `0x8000c89a`/`0x8000c7ee`/`0x8000c742` | [C] |
| 8 | 2 | TICK | self; `FUN_8000AF40(3, delta)` → `0x2563` | `0x8000c948` | [C] |
| 9 | 6 | TICK | self; `FUN_8000AB24(delta)` → `0x2558` | `0x8000c69c` | [C] |
| 10 | 2..6 | **LONG PRESS** | self; **toggles mute, starts LED 0x22 blinking** | `0x8000CBC8`..`0x8000CBEF` (40 bytes) | [C] |
| 11 | 3/4/5 | `0x255C` changed | 3/4/5 to match | `FUN_8000CAF0`, store `0x8000cb2c`; sole caller `0x8000b75c` (work-queue arm 5) | [C] |
| 12 | any | USB suspend | 1 (old state → `0x1B94`) | `0x80010ad6` / `0x80010bda` | [C] |
| 13 | 1 | USB resume | restored from `0x1B94` | `0x80010b1e` / `0x80010c04` / `0x80010c76` | [C] |
| 14 | any | vendor `0x48` SET 0/1/2 | 2 / 3·4·5 / 6 | `0x80009252` / `0x80009342`,`0x80009392` / `0x8000930a` | [C] |
| 15 | any | vendor `0x48` SET 1, type==2 | **no change** (firmware bug) | `0x80009388 585c cp.w r12,0x5 / brne 0x800090ce` | [C] |
| 16 | any | vendor `0xA0` | 6 or 8 | `0x80009122 movne r12,0x6` / `0x80009126 moveq r12,0x8` → `0x8000912a` | [C] |
| 17 | 8 | — | button entirely ignored | `0x8000cb4c` | [C] |
| 18 | — | — | **7 is never entered** | all 15 stores to `0x2648` write {0,2,3,4,5,6}; all 10 callers of `FUN_8000C3F4` pass {1,2,3,4,6,8,saved} | [C] |
| 19 | 2..6 | long press, latch already set | nothing | `0x8000cbc6 cd31 brne 0x8000cb6c` | [C] |
| 20 | 2..6 | release after long press | latch cleared, countdown reloaded, **no focus advance** | `0x8000cc76`..`0x8000cc8e` | [C] |

### Where the code disagrees with the owner's description — plainly

**There is no monitor-volume mode in this firmware.** [C]

The owner describes: long press → monitor-volume mode, volume indicator blinks; then presses light the mic / instrument indicator and the knob adjusts a *monitor* level; long press again returns.

What `0x8000CBC8` actually does, read instruction by instruction from the bytes: `rcall 0x8000a208` (read mute byte `0x2550`), `eorl r12,0x0001`, `rcall 0x8000ab84` (write it back inverted), `rcall 0x8000c4e8` (arm blink-A on LED `0x22`). That is a **mute toggle**. The same byte is what vendor request `0x35` — Output Mute — reads and writes. [C]

The owner's observations are all individually accounted for by this:

- "volume indicator starts blinking" → blink-A on LED `0x22`, the indicator that state 6 (output focus) lights. [C]
- "pressing lights the mic indicator, then the encoder adjusts mic level" → the ordinary focus ring is untouched by the long press, so the next press advances focus to the mic and the knob adjusts **mic gain** (`FUN_8000AF40`, RAM `0x2560+type`), not a separate monitor level. [C]
- "long press again returns to normal" → the second long press toggles mute back off, which stops the blinking. Indistinguishable from "exiting a mode" unless you listen to the output. [C]

The one claim the code does **not** support is that the knob is on a second, separate monitor volume. I verified this negatively: the only encoder targets in the whole machine are `FUN_8000AF40(0..3, delta)` → the 4-byte gain array at `0x2560`, and `FUN_8000AB24(delta)` → `0x2558`. Neither function reads the mute byte `0x2550` or the blink flag `0x2650`, so neither behaves differently muted or not. [C]

**This matters for the patch and the owner should settle it before flashing** (§4, experiment 1). It is a one-minute USB read. Either the owner's unit runs different firmware than this image — in which case none of the addresses below apply — or "monitor-volume mode" is the mute-and-blink state read from the outside.

---

## 2. The hook

### Exact address and the instruction currently there

```
0x8000CBC8   file offset 0x0CBC8   bytes: fe b0 eb 20   =  rcall 0x8000a208
```

This is the first instruction of the 40-byte long-press block `0x8000CBC8`..`0x8000CBEF` (`0x8000CBF0 − 0x8000CBC8 = 0x28`). [C] — verified by disassembling the whole function this session.

### Register state on arrival — this is what makes the hook cheap

I traced every path into `0x8000cbc8` and there are no calls between the definitions and the hook, so:

| Reg | Value at `0x8000CBC8` | Why | C/H |
|---|---|---|---|
| **r6** | **the current focus state (2..6)** | `ld.w r6,r7[0x0]` at `0x8000cb56`; nothing writes r6 and nothing is called on the path `cb56→cb5a→cba6→cba8→cbaa→…→cbc8` | **[C]** |
| **r7** | **`0x2648`** | `mov r7,0x2648` at `0x8000cb46`; the only call on the path is `rcall 0x8000d584`, whose entire body uses only r8/r9/r10/r12 | **[C]** |
| r8 | 0 | `ld.sh r8,r7[0x10]`; `brne` at `cbbc` not taken | [C] |
| LR | dead | saved to stack by `stm --sp,{r5-r7,lr}` at `0x8000cb40`; the epilogue pops PC from that slot | [C] |

So **"does the mic have focus"** is two compact compares against a register that is already loaded: `cp.w r6,0x2` / `cp.w r6,0x6`. States 3,4,5 are everything else in range. No reload, no call.

### What the patched code must do

```
  cp.w r6, 0x2  ─┐ either -> keep the stock mute toggle
  cp.w r6, 0x6  ─┘
  ── else: mic has focus (state 3, 4 or 5) ──
  0x265C = 1                      ; one-shot latch, so one step per hold
  r12 = FUN_8000A248()            ; current source, 0/1/2
  r12 = r12 + 1 ; if r12 == 3 then r12 = 0
  r11 = 4
  FUN_8000AA30(r12, r11)          ; set the source
  back to 0x8000cb6c
```

Three design points, each resting on bytes I read this session:

**(a) `FUN_8000AA30(type, 4)` is the whole job — do not call `FUN_8000CAF0` or `FUN_8000A250`.** The traces' plan had the patch call the resync and the GPIO switch itself. That is unnecessary and would double-drive the hardware. `FUN_8000AA30` stores `0x255C` and posts record 5 slot +4 of the work array at RAM `0x42C`; the main loop's `rcall 0x8000b6d0` at `0x80010eda` services it and its dispatch entry 5 is `0x8000b75c = rcall 0x8000caf0 / rcall 0x8000a250` — **the focus resync and the analog/48V switch, already wired together.** [C] — I hexdumped the 8-entry table at `0x8000A014`: `b7a0 b6fe b78a b774 b768 b75c b746 b72a`.

**(b) mode = 4, not 3.** `0x8000aa64 cp.w r11,0x3 / c2e0 breq 0x8000aac2` jumps *past* `0x8000aa6c st.w r7[0x94],r8`, the store that posts record 5 slot +8 — and record 5 +8 is exactly what raises vendor `0x29` mask bit 4 (`a5a9 sbr r9,4` at `0x8000b828`, guarded by index==5). So **mode 3 changes the source but never tells the host app.** [C] Mode 4 takes the `0x8000aa70 cp.w r11,0x4` branch *after* that store, so bit 4 is raised. [C] And mode 4 is not a guess: it is the value Apogee's own locally-originated path passes — `0x80007434 304b mov r11,0x4` / `0x80007438 rcall 0x8000aa30`, the UAC2 Selector-Unit worker. **[C]** Using 4 means the Maestro software's input-source display follows the knob.

**(c) the modulo-3 wrap must stay a wrap, and must never emit ≥ 3.** `FUN_8000AA30` does **no** range check (`0x8000aa44 913c st.w r8[0xc],r12` stores whatever arrives), and `FUN_8000A250` *silently returns* for any type ≥ 3 (`0x8000a2e4`-area: `cp.w r8,0x2 / c111 brne 0x8000a282`, and `0x8000a282` is `d802 popm {pc}`). [C] A patch that let the counter reach 3 would leave the mic dead with no indicator change and `0x36` GET reporting 3.

### Is the call safe from this context?

**Yes, and it is safe twice over.** [C]

- `FUN_8000AA30` is non-blocking: 57 instructions in its full closure, one callee (`FUN_8000CCC4`, which I disassembled — 11 instructions, RAM `0x26D8` only), no peripheral base materialised anywhere, no spin loop, no `ssrf`/`csrf`/`mfsr`, 12 bytes of stack.
- It preserves everything the hook needs. `stm --sp,{r7,lr}` saves and restores r7, and neither it nor `FUN_8000CCC4` touches r5 or r6. So **r7 is still `0x2648` on return**, which is required by `0x8000cb6c` (`ld.ub r10,r7[0x8]`). I checked this explicitly because it is the one thing that would silently corrupt the blink state.
- Apogee already calls it from a deeper and more hostile context: the vendor `0x36` SET handler runs inside the **USB interrupt handler** (the function registered at `0x80005cf8`, whose only epilogue is `ldm sp++,{r5-r7,lr}` at `0x80005d64` followed by `d603 rete`). Our hook runs in the main loop at ordinary priority — strictly safer than a path the vendor ships. [C]

One residual, honestly: `FUN_8000AA30` is not re-entrant. `ld.w r9,r8[0xc]` / `cp.w r9,r12` / `breq` / `st.w r8[0xc],r12` (`0x8000aa3a`..`0x8000aa44`) is an unguarded test-then-set with no interrupt masking, and the USB ISR can already call it. The patch makes that a three-caller race instead of two. The window is four instructions and the worst case is a lost or duplicated source change, not corruption. [C] I would not add masking — the stock firmware doesn't, and adding it is more risk than the race.

### The "how does the user get back" problem — the premise is different from what the owner thinks

The task frames this as "long press in that state currently returns to normal mode". **It does not.** In this image long press toggles mute, and there is no mode to return from — the focus ring keeps working underneath at all times. [C] So nothing needs a new exit: **a short press still advances the focus ring exactly as before, from any state.**

What the patch actually costs is **mute, in the three mic-focus states only**. The honest options, for the owner to choose:

| | Behaviour | Mute still reachable from the panel? | Size | Risk |
|---|---|---|---|---|
| **A (recommended)** | Long press cycles the source in states 3/4/5; long press still toggles mute in states 2 (instrument) and 6 (output) | **Yes** — short-press to the instrument or speaker stop, then long-press. Both are 1–2 presses away | 78 B out of line + 4 B hook | lowest; the mute code is bit-for-bit Apogee's |
| B | Long press cycles the source in all five focus states | No — only via USB vendor `0x35` / Maestro | fits **in place**, 26–34 B of the 40 | no trampoline needed, but the panel loses mute entirely |
| C | Keep mute at 105 passes; add a second, longer threshold (~300) for the source cycle | Yes, unchanged | needs a second countdown field + ~40 B more | highest; needs a new RAM field (`0x264C` is free — 8 writers, 0 readers [C]) and a second timer, and the owner must learn two hold durations |

I recommend **A**. It is the only one that takes nothing away, it matches the owner's request literally ("when the mic indicator has focus"), and the block is *already* gated to states 2..6 so no extra range test is needed. [C]

**Two behavioural consequences the owner should know before choosing** (both [C]):

1. **One step per hold.** The latch `0x265C` means the source advances once per press-and-hold; Internal → External+48V is two separate long presses. I kept it that way deliberately: auto-repeat would let a careless hold run past External and **switch 48V phantom power on**, which `FUN_8000A250` applies immediately (`e360(0x0d,1)`, `e360(0x0e,1)`). With a ribbon mic or an unbalanced source on the XLR that is the one outcome in this whole project that can damage hardware outside the ONE. If the owner would rather the cycle stop at External and leave 48V to the host app, that is a two-byte change (compare against 2 instead of 3) and I would support it.
2. **States 4 and 5 light the same selection LED** (`0x0f`, PB23). The visual difference between External and External+48V is the separate 48V indicator `0x0e` (PB22), driven by `FUN_8000A250`, not by the focus handler. So the three steps look like: LED `0x10` → LED `0x0f` → LED `0x0f` **+** `0x0e`. The owner should expect that, not three distinct icons.
3. Each source keeps its own gain (`0x2560`/`0x2561`/`0x2562`), so cycling the source also changes what the knob is adjusting. That is stock behaviour, not something the patch introduces. [C]

---

## 3. Space and safety

### It does not fit in place, and here is the exact shortfall

I costed the tightest possible in-place version that keeps both gestures, sharing the latch store between the two arms and shortening the mute arm as far as it will go:

```
  6 B   latch:  mov r8,0x1 / st.b r7[0x14],r8
  8 B   test:   cp.w r6,0x2 / breq / cp.w r6,0x6 / breq
 18 B   mic arm (no latch, no trailing branch counted twice)
 16 B   mute arm, absolute minimum
 ───
 48 B   vs. 40 B available
```

**Eight bytes short.** [C] So option A needs a trampoline; only option B (drop mute) fits in place.

### Where the trampoline goes — and why not the free tail

I used **state 7's handler, `0x8000C5D4`..`0x8000C65B`, 136 bytes.** I did not take "state 7 is dead" on trust; I closed it three ways this session:

- All 15 stores to `0x2648` write only {0,2,3,4,5,6}; all 10 callers of `FUN_8000C3F4` pass {1,2,3,4,6,8} or a value restored from `0x1B94` (which only ever held those). **Complete enumeration of both write paths — 7 is unreachable.** [C]
- **Zero** branches or calls from outside the region into it, over a full instruction-aligned sweep of the application body. [C]
- **Exactly one** 32-bit word in the whole 98,488-byte image points into it: `0x8000C3A8` = `0x8000C5D4`, which is vtable entry 7 itself. [C]
- Its LED-bitmask companion `FUN_8000C4A0` is called only from `0x8000C332` and `0x8000C382`, both inside the battery/power routine — **no vendor request drives state 7**, so this is not a host feature I would be breaking. [C]

**I deliberately did *not* use the free tail** (`0x800180B8`..`0x80020000`, 0x7F48 bytes), even though it is the obvious place. The project's own `FLASHING.md` records that the updater writes a fixed window — start `0x4000`/`0x24000`, length `0x1C000` — while Image0 is only `0x180B8` long and Image1 `0x380B8`. Both files are *shorter than the window the updater writes*, so the updater must either pad or truncate, and **which one is unverified**. If it truncates, appended bytes never reach flash and the `bral` lands in unknown flash. That failure is recoverable (the device still boots and enumerates; it only misbehaves on a long press, so it stays re-flashable) but it is an avoidable unknown. Using dead code inside the existing image removes it entirely. §4 experiment 4 says how to settle it cheaply if the owner ever wants the tail.

**Do not "tidy up" vtable entry 7** at `0x8000C3A8` to stop anything entering the trampoline through the table. It currently holds `0x8000C5D4` in Image0 and `0x8002C5D4` in Image1 — it is one of the 662 relocated words. Leaving it alone is automatically bank-correct; changing it would mean hand-maintaining the `+0x20000`. And it is harmless: if state 7 somehow became current, the tick would `icall` the trampoline with r6=7, which falls to the mic arm and returns via `bral 0x8000cb6c` into a correctly-framed function. Wrong, but not a crash. [C]

### The patch

Three edits per image. **File length unchanged** (98,488 / 229,560) — verified.

```
file 0x0C5D4 (Image0) / 0x2C5D4 (Image1)   78 bytes   trampoline:
  5826 c110 5866 c0f0 3018 ef68 0014 feb0
  ee33 2ffc 583c c021 300c 304b feb0 f220
  e08f 02bc feb0 ee08 1898 ef68 0008 3018
  ec1c 0001 ef68 0014 301b feb0 f2bb ef3c
  0008 ec1c 0001 feb0 ff67 e08f 02a7

file 0x0CBC8 (Image0) / 0x2CBC8 (Image1)    4 bytes   hook:
  fe9ffd06                 was feb0eb20

file 0x0CBCC (Image0) / 0x2CBCC (Image1)   36 bytes   optional nop fill:
  d703 x 18
```

Disassembled back out of the patched image by the same decoder:

```
8000c5d4 5826      cp.w r6, 0x2
8000c5d6 c110      breq 0x8000c5f8          ; instrument focus -> mute
8000c5d8 5866      cp.w r6, 0x6
8000c5da c0f0      breq 0x8000c5f8          ; output focus    -> mute
8000c5dc 3018      mov r8, 0x1
8000c5de ef680014  st.b r7[0x14], r8        ; 0x265C latch = 1
8000c5e2 feb0ee33  rcall 0x8000a248         ; r12 = mic source
8000c5e6 2ffc      sub r12, -0x1            ; +1
8000c5e8 583c      cp.w r12, 0x3
8000c5ea c021      brne 0x8000c5ee
8000c5ec 300c      mov r12, 0x0             ; wrap 3 -> 0
8000c5ee 304b      mov r11, 0x4             ; local change; raises 0x29 bit 4
8000c5f0 feb0f220  rcall 0x8000aa30
8000c5f4 e08f02bc  bral 0x8000cb6c
8000c5f8 feb0ee08  rcall 0x8000a208   <-- MUTE arm: Apogee's 40 bytes verbatim,
8000c5fc 1898      mov r8, r12             only the closing 2-byte rjmp became
8000c5fe ef680008  st.b r7[0x8], r8        a 4-byte bral
8000c602 3018      mov r8, 0x1
8000c604 ec1c0001  eorl r12, 0x0001
8000c608 ef680014  st.b r7[0x14], r8
8000c60c 301b      mov r11, 0x1
8000c60e feb0f2bb  rcall 0x8000ab84
8000c612 ef3c0008  ld.ub r12, r7[0x8]
8000c616 ec1c0001  eorl r12, 0x0001
8000c61a feb0ff67  rcall 0x8000c4e8
8000c61e e08f02a7  bral 0x8000cb6c
```

78 of 136 bytes used, **58 spare**. The 58 bytes at `0x8000C622`..`0x8000C65B` are leftover state-7 fragments; nothing reaches them (my own code ends in `bral`), but nop-filling them is free and I would do it.

Every encoding is copied from real bytes in this image rather than assembled from the manual: `3018` from `0x8000cbd2`, `ef680014` from `0x8000cbd8`, `304b` from `0x80007434`, `5826` from `0x8000cba6`, `5866` from `0x8000cb58`, `583c` from `0x8000c66a`, `300c` from `0x8000c43e`. Only three forms are computed — `rcall`/`bral` (k21) and the compact `breq`/`brne` (disp8) — and all three round-trip through the decoder, which is the real check. `bral` is cond4=15 and occurs **126 times** in the stock image; I hand-verified `fe9ffd64` at `0x80006288` → `0x80005D50` against the field layout before using the form. [C]

### Both banks — verified, not argued

This is the part I was most worried about, and it has a clean answer. The two stock bodies are **not** identical: 662 four-byte words differ, **every single one by exactly `+0x20000`, and every one holds a value inside `0x80004000`..`0x800180B8`.** So the banks differ only in absolute code-address literals (the vendor tables, the vtable, callback pointers); every instruction encoding, including every PC-relative branch, is byte-identical. [C]

The rule that follows: **a patch built only from PC-relative instructions is bank-agnostic — the same bytes at file offset X and X+0x20000. Any absolute address literal must be written twice, +0x20000 apart.** My patch contains no absolute literal, by design.

Verified end to end:

```
pre-patch: all three target regions byte-identical across banks ....... True
file lengths after patch: 98488 / 229560 ............................. unchanged
differing words between banks after patch ............................ 662  (stock: 662)
words whose bank delta != +0x20000 ................................... 0
every trampoline instruction re-decoded out of Image1 ................ same mnemonic,
                                                                       target +0x20000
hook  bank0: bral 0x8000c5d4      bank1: bral 0x8002c5d4
DUAL-BANK RESULT: PASS
```

The patch introduces **zero** new divergence between the banks. [C]

### Recoverability

Per `FLASHING.md` [C, prior project work]: the updater writes the **inactive** bank only, never touches the bootloader at `0x0`–`0x4000`, and verifies each page by read-back. The patch touches no boot, clock, USB or enumeration code — only the UI tick and a dead handler in the same module. Worst case is a device that boots, enumerates and answers USB but misbehaves on a long press, which is always re-flashable. Keep the other bank stock for the first flash.

Candidate images, for review only — **not yet approved for flashing**:
```
<scratch>\sm\Image0.micsrc.bin   98488 B  sha256 0bd5ea7c7da46deeec081109f095ea2e...
<scratch>\sm\Image1.micsrc.bin  229560 B  sha256 89aa7432a9ad9a45079e8945c5908e83...
build script: ...\scratchpad\sm\mk.py      disassembly helper: ...\scratchpad\sm\d.py
```

---

## 4. What is still unknown, and the cheapest experiment for each

### Free — USB reads while a human presses buttons. Minutes, no flashing, no risk.

**1. Does "monitor-volume mode" exist? (the one that could invalidate everything above)** — **do this first.** Long-press the encoder until the indicator blinks, then read `control_transfer(0xC0, 0x35, 0, 0, 1)`. If it returns `1`, the long press is Output Mute and the owner's model needs correcting — the patch above is right. If it returns `0` while an indicator is blinking, this image is not what the owner's unit runs, and **no address in this report applies.** Cross-check by ear: the output should be silent while blinking. *Settles: §1's central disagreement, and whether to build the patch at all.*

**2. Which indicator does the owner call "the volume indicator"?** While blinking, note which LED it is; then short-press through the ring and note which stop lights that same LED. It should be the stop where the knob changes output volume (state 6, LED `0x22`, PA02). *Settles: the [H] icon naming. One look.*

**3. The focus ring and the grouping flag.** Poll `control_transfer(0xC0, 0x48, 0, 0, 1)` repeatedly while short-pressing. Expect the cycle `2 → 1 → 0 → 2` (output → mic → instrument) with grouping off, and `2 → 1 → 2` with it on. If the instrument stop never appears, `0x257C` is set and option A's "long-press the instrument stop to mute" is unavailable — the owner would mute from the speaker stop instead. *Settles: transition rows 4–6, and an ergonomic detail of option A.*

**4. Long-press duration in milliseconds.** Stopwatch the hold. 105 passes × 10 RTC ticks is [C]; converting to seconds needs the UC3A3 peripheral datasheet, which is not in `resources`. The button-timing estimate of ~1.17 s is **[H]** and rests on RCSYS at a nominal 115 kHz with PSEL=6 — an untrimmed RC oscillator. Nothing in the patch depends on it; it only matters if the owner later wants option C's second threshold. *Settles: the only remaining [H] in the timing chain.*

**5. Does the mic source cycle reach the host app?** After flashing: drain `0x29` by reading it twice (it is **read-to-clear** — `0x8000a1d0` loads and zeroes `0x2538` in adjacent instructions [C]), long-press in mic focus, then read `0x29` once. Byte 2 should have **bit 4** set, and `control_transfer(0xC0, 0x36, 0, 0, 1)` should report the new source. This is the direct test of the mode-4 choice. *Settles: whether Maestro's display follows the knob.*

**6. The out-of-range hole, as a read-only validation of two decodes.** `control_transfer(0x40, 0x36, 0, 0, [7])` should leave the audio path audibly unchanged while `0x36` GET reports `7`, because `FUN_8000A250` silently returns for type ≥ 3. Recoverable by setting it back to 0/1/2. This confirms from outside the firmware that `0x8000aa44` stores unchecked and `0x8000a282` is a bare return. *Settles: the [C] basis for design point (c).*

### Needs work, but each is bounded

**7. Does the updater write past end-of-file?** Only matters if the owner later wants the free tail. Cheapest: append a recognisable 16-byte pattern at `0x180B8`, flash, then read that flash range back with the `0xA9` sub-commands the project already has. If it comes back, the tail is usable and there is 0x7F48 bytes of room for anything larger. *Not needed for this patch.*

**8. What is work-array slot `+12`?** Two dispatchers scan RAM `0x42C` at `+4` (`0x8000b708`, hardware apply) and `+8` (`0x8000b80e`, host notify); a third walk starts at `0x8000b860` with `sub r10,r4,-0xc` and I did not decode it. [C] that it exists, [H] what it consumes. Mode 4 skips `+12`, and mode 4 is what Apogee's own local path uses — so whatever it is, skipping it for a local change is the vendor's own choice, which is why I am comfortable. Settle it by reading the `0x8000b860` loop and its jump table.

**9. The `cp.w r12,0x5` oddity at `0x80009388`.** I re-read the bytes `58 5c fe 91 fe a2 cc ea` and confirmed by hand against the compact `CP.W Rd,imm6` layout (`01011 imm6 Rd`, cross-checked against `0x581c`/`0x582c`/`0x5868`/`0x5888` elsewhere in the module) that it is `cp.w r12,0x5`, not `mov r12,0x5` (which would be `0x305c`). The effect is that **vendor `0x48` SET=1 does nothing when the mic source is External+48V** — an apparent firmware bug, not a decode I distrust. [C] It does not touch the patch. If the owner wants it fixed, changing `585c` → `305c` at file `0x9388` would make that path set state 5, but I have not analysed the consequences and would not bundle it with this change.

**10. Which physical pin is behind each indicator id.** `FUN_8000E360` indexes a 35-entry table built at run time into RAM `0x2a4c` by `FUN_8000E394`; I read the builder and the ids the patch cares about are `0x0f`=PB23, `0x10`=PB24, `0x11`=PB31, `0x22`=PA02, `0x0e`=PB22, `0x0d`=PB20 — all four task-supplied ids (`0x0d`,`0x0e`,`0x18`,`0x19`) match. [C] Still [H]: that `0x0d` is the 48V *supply* and `0x0e` the 48V *LED* rather than the reverse. The usage asymmetry supports it (`0x0d` appears at only two sites, both inside `FUN_8000A250`; `0x0e` also appears in the Identify state and in the blank/restore table), but without a schematic it is an inference. It does not affect the patch, which never touches either id directly.

### Two things I want on the record as *not* unknown

- **State 7 being dead** is a complete enumeration, not a sample: every store to `0x2648`, every caller of `FUN_8000C3F4`, every branch into the region, and every word pointing at it. That is what licenses putting the trampoline there. [C]
- **The dual-bank behaviour** is verified empirically by patching both images and re-diffing, not argued from the relocation theory. [C]

The single thing standing between this report and bytes in flash is **experiment 1**. If the long press turns out not to be mute, stop and re-map before flashing anything.