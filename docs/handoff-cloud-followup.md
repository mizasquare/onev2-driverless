# Follow-up for the cloud session that produced `EP0_PIPELINE_MAP.md`

Read this before doing anything else. Three things have changed: **the goal that motivated your map
has been reached by a different route**; one of your results that I publicly doubted turns out to be
correct; and the central premise of the brief I gave you — "this firmware implements no UAC2 class
requests" — is **disproved by hardware measurement**. The remaining work is different from, and
smaller than, what the original brief implied.

Same ground rules as before, and they matter more than speed:

- Label every statement **[C] confirmed** (say how: bytes read / decompiler / authoritative doc) or
  **[H] hypothesis**. A round of this project was lost to an unlabeled inference presented as fact,
  and a second round was lost to *my* unlabeled inference. See §2.
- Analyse `ONEv2_USB_Audio_Image0.bin` (bank 0, linked at `0x80004000`). Image1 is the same body
  relocated `+0x20000`.
- Do **not** propose descriptor changes. The descriptor is finished and working; see §1.

---

## 1. Status change: [P1] is done, and no code patch was involved

Windows 11 now drives the ONEv2 with its inbox `usbaudio2.sys` and **no vendor driver and no host
application**. Capture and playback both work. **[C, measured on hardware]**

- `ONEv2` device node `problem=0`, status OK; four `AudioEndpoint` children OK
  (`마이크(ONEv2)` ×3 + `스피커(ONEv2)`); zero `usbaudio2` events in the System log.
- Capture: Internal Mic, hardware gain 35 dB, 44.1 kHz stereo, 3 s → peak −45.0 dBFS, rms
  −55.6 dBFS, no overflow. Proven to be the real analog path: sweeping the hardware preamp 0→45 dB
  moved the noise floor −87.8 → −45.9 dBFS, **43.5 dB, monotonic**.
- Playback: a WASAPI output stream opens and runs (fed silence deliberately).
- **Rates:** exclusive-mode WASAPI runs the device at 44.1 / 48 / 88.2 / 96 kHz; 32 and 22.05 are
  rejected. See §2c — this is also the proof that class requests work.
- **Input switching works from the host**, with no vendor channel involved: the three capture
  endpoints map 1:1 to the three selector positions. Also §2c.
- Idle 16 min / 23 samples: zero `usbaudio2` events, `problem=0` and 4 endpoints throughout.
- Live config descriptor is 328 bytes, `bcdDevice` 1.09, device enumerates at USB 2.0 high speed.

**Field tests are in, and they move the goalposts.** On **macOS** the patched firmware does
capture, playback **and input source switching from Audio MIDI Setup's Source popup** — Apple's
class driver does expose `SELECTOR_UNIT 15` with the current topology (terminals directly on the
pins, `iSelector = 0`), so nothing there regressed. On **iPad USB-C**, playback works and **capture
never registers** — exactly as on the untouched original firmware, so it is not a regression but
the one goal still unmet. Everything below should be read with that as the target.

**It took six descriptor rounds and zero bytes of code.** The three defects that actually mattered
were all original Apogee bugs that had never been exercised because no host had ever parsed this
descriptor successfully:

1. **A spec violation.** ADC-2 §4.7.2.8: `FEATURE_UNIT bLength = 6 + (nch+1)×4`, so 18 for a
   2-channel cluster. The firmware declared **10** for all four FUs, i.e. "zero logical channels".
   This was the only outright spec violation in the whole 332-byte descriptor, and it is what
   Event ID 34 was about. To make room, the three mic FUs were merged into one FU behind the
   selector: `IT 9/11/13 → SU 15 → FU 10 (2 ch, bLength 18) → OT 8`.
2. **Advertising controls that do not exist.** Mic `FEATURE_UNIT 10` declared volume controls the
   firmware does not implement (Apogee's software uses vendor `0x34` for gain, so there was never a
   reason to implement them). Zeroing its `bmaControls` cleared one STALL.
3. **Pointing at a string that does not exist.** `SELECTOR_UNIT 15` had `iSelector = 21`. Only
   string indices 1, 2, 3 and 17–20 exist on this device; every other index STALLs. Setting it to 0
   was the last change, and `problem=0` followed.

Round-by-round: R1 IAD/`wTotalLength`/duplicate clock id → Event 34 persists (useful side effect:
IF3 split into its own node `MI_03`, which is where WinUSB now binds). R2 remove the duplicate
`CLOCK_SOURCE` → persists. R3 clock `bmAttributes` 0x01→0x03, iso endpoints Sync→Adaptive/Async,
capture `bmChannelConfig` 0x04→0 → persists. R4 **FU `bLength` 10→18 → Event 34 stops, Event 38
begins**. R5 zero mic FU `bmaControls`. R6 `iSelector` 21→0 → `problem=0`.

So the plan in §2/§3 of the brief I gave you — insert a UAC2 class handler in free flash — **was
never executed and is not needed for Windows.** It may still be needed for iPad; see §4.1.

---

## 2. Corrections to the record

### 2a. Your hook encoding `e08fbf48` is CORRECT. My refutation was wrong.

I told you the 4-byte branch form carries a 16-bit displacement, that `0xBF48` therefore meant
`−16568` halfwords, and that your hook would branch to the reset vector and boot-loop the device. I
backed this with "1154/1154 targets land inside the image under my reading, 647/1154 under the
rival reading".

That was best-fit reasoning over two hypotheses I happened to think of, and the truth was a third.
The AVR32 Architecture Document (32000D–04/2011, p.143–144) gives `BR{cond4} disp21` Format II as:

```
bits 31..29 = 111
bits 28..25 = disp21[20:17]
bits 24..21 = 0100              <- opcode
bit  20     = disp21[16]
bits 19..16 = cond4
bits 15..0  = disp21[15:0]
PC <- PC + (SE(disp21) << 1)    range +/- 1 MB
```

Verified against this image: `e085 00cf` has bits 19..16 = `0101` = `lt`; `e081 00f3` has `0001` =
`ne`. The displacement is **21 bits**, with its high bits and sign in the *first* halfword — fields
that are zero in all 1154 long branches here because every real displacement in this image is
positive and below `0x10000` halfwords. That is precisely why my empirical test could not separate
the readings. **`e08f bf48` = `disp21 0x0BF48`, sign clear, target `0x80020000`. Correct.** And a
backward branch of any size within ±1 MB is fine, so the return path is not a problem either. **[C,
authoritative doc + bytes]**

### 2b. Your bank-1 target `0x80040000` is still wrong, for an unrelated reason

The flash address decode on this part **ignores bit 18**. `read(x)` and `read(x + 0x40000)` return
byte-identical data for every pair tested (`0x0`/`0x40000`, `0x1000`/`0x41000`, `0x4000`/`0x44000`,
`0x8000`/`0x48000`, `0x20000`/`0x60000`). So `0x80040000` **aliases onto `0x80000000`, the
bootloader reset vector** — a single page written there is unrecoverable without JTAG. Our flasher
now refuses any address outside `0x80000000`–`0x8003FFFF`, and refuses a page that crosses a bank
bound. **[C, live reads]** Bank 1 needs its own displacement; the two banks cannot share these bytes
unless hook and target both relocate by `+0x20000`.

### 2c. The brief I gave you was wrong: this firmware DOES implement UAC2 class requests

The brief stated, as **[C, decompiled]**: "`FUN_80008432` handles only `SET_INTERFACE`; there is no
class-request handling at all — the firmware implements no USB Audio Class 2.0 control requests."

**That is false.** Two independent host-side experiments on the R6 firmware show the firmware both
answers and acts on UAC2 class control requests. **[C, measured on hardware]**

**Experiment 1 — the clock really retunes.** In WASAPI *exclusive* mode (no audio-engine
resampling; frames move at the device's own clock) the device accepts 44100, 48000, 88200 and
96000 Hz and rejects 32000 and 22050. One second of output frames takes 1.013 / 1.016 / 1.016 /
1.016 s of wall clock at those four rates — 43524 / 47257 / 86784 / 94457 frames per second
apparent — so it is genuinely running at each one. Under UAC2 a host changes the rate only via
`SET CUR, CS_SAM_FREQ_CONTROL` on the clock entity, and it can only *learn* that rate list from
`GET RANGE, CS_SAM_FREQ_CONTROL`, because a UAC2 `FORMAT_TYPE` descriptor carries no rate list at
all. A device-specific set of exactly four rates therefore came off the wire. (Shared mode accepts
only 44100, because the endpoint's default format is 44.1 kHz — that path proves nothing, which is
why this has to be done in exclusive mode.)

**Experiment 2 — the selector obeys the host, and the firmware's own state follows.** Windows
created three WASAPI capture endpoints. Holding a WinUSB handle on IF3 throughout (it coexists with
`usbaudio2`), forcing the firmware's input-type variable to 0 over vendor `0x36`, then opening one
endpoint and polling `0x36` eight times during the stream:

```
no stream open, forced to 0        ->  stable at 0 for 20 s (40 polls)
forced to 0, open capture ep #1    ->  0 then 0 0 0 0 0 0 0 0   (Internal Mic)
forced to 0, open capture ep #0    ->  0 then 1 1 1 1 1 1 1 1   (External)
forced to 0, open capture ep #2    ->  0 then 2 2 2 2 2 2 2 2   (External +48V)
forced to 2, open capture ep #0    ->  2 -> 1                   (External; switches both ways)
forced to 1 / to 2, no stream      ->  holds at 1 / at 2
```

Each capture endpoint maps 1:1 to a selector position; opening it drives the selector; and the
firmware honours the request by updating `0x255C`, the same variable vendor `0x36` reads. The only
way a host can do that is `SET CUR` on `SELECTOR_UNIT 15`. Nothing moves while no stream is open, so
this is not the firmware switching itself. **This is the finding the entire iPad goal rested on.**

An earlier run of this test seemed to show an asymmetry — that the host issued the `SET CUR` only
when the current value was 0. **That was my measurement artifact, not device behaviour, and it is
withdrawn.** A failed vendor request had re-enumerated the device mid-run, which silently
invalidates every PortAudio device index in the process, so the later trials were opening a
different endpoint than the one they named. Re-run with indices resolved immediately before each
open, the selector moves from any starting value in either direction.

**Experiment 3 — the wire, directly.** An ETW capture of `Microsoft-Windows-USB-UCX` (the provider
that carries the 8-byte SETUP packets; USBXHCI does **not** — it only logs xHCI slot/endpoint/TRB
activity) over two 30-second windows, with the device driven through clock retunes, each capture
endpoint, and selector changes in both directions:

```
run A: 28 class requests, 28 answered, 0 STALLed
run B: 27 class requests, 27 answered, 0 STALLed

  x8  OUT CUR  CLOCK_SOURCE 1     SAM_FREQ  iface=0  OK(0x00000000)
  x8  IN  CUR  FEATURE_UNIT 4     VOLUME    iface=0  OK(0x00000000)
  x8  IN  CUR  FEATURE_UNIT 4     MUTE      iface=0  OK(0x00000000)
  x4  OUT CUR  SELECTOR_UNIT 15   SELECTOR  iface=0  OK(0x00000000)    (x3 in run B)
```

What matters in it:

- **Nothing STALLs.** Every class request the host sends is answered.
- **`FEATURE_UNIT 10` (capture) receives nothing at all.** The R5 patch that zeroed its
  `bmaControls` does exactly what it was meant to: the host stops asking for controls the firmware
  does not implement.
- **No `GET RANGE` and no `CLOCK_VALID` in these windows** — Windows read them once at bind time and
  cached them, so this capture does not speak to `GET RANGE`. An earlier pre-R6 capture does:
  `FEATURE_UNIT 4 VOLUME GET RANGE` answered `OK` 77 times in one minute.
- The selector `SET CUR` count matches the number of real transitions (4 transitions, 4 requests in
  run A). The data stage was not captured, so the pin value actually written is unverified.
- Vendor and class traffic interleave on the same device with no interference: `0x28` ×56, `0x36`
  ×28, `0x29` ×1, all `OK`, alongside the class requests.
- `SET_INTERFACE` alt 1 → alt 0 cycles on interface 1 (playback AS) and interface 2 (capture AS),
  all `OK`. No `GET_DESCRIPTOR` and no re-enumeration inside the windows.

**So the interface-3 STALLs below are interface-mismatch rejections, not a missing handler** — which
also tells us the handler checks the interface byte of `wIndex`. For the record, every UAC2 class GET
aimed at interface 3 (the only interface libusb will let us address, since `usbaudio2` owns the
AudioControl interface):

```
bmRequestType 0xA1 (IN | class | interface), wIndex = entity<<8 | 3
  IOERR   CLOCK_SOURCE 1   sam freq      GET CUR     -> [Errno 5] I/O Error
  GONE    CLOCK_SOURCE 1   sam freq      GET RANGE   -> handle went stale
  STALL   CLOCK_SOURCE 1   clock valid   GET CUR     -> [Errno 32] Pipe error
  STALL   SELECTOR_UNIT 15 selector      GET CUR     -> [Errno 32] Pipe error
  STALL   FEATURE_UNIT 10  mute   ch0    GET CUR     -> [Errno 32] Pipe error
  STALL   FEATURE_UNIT 10  volume ch1    GET CUR     -> [Errno 32] Pipe error
  STALL   FEATURE_UNIT 10  volume ch1    GET RANGE   -> [Errno 32] Pipe error
  STALL   FEATURE_UNIT 4   mute   ch0    GET CUR     -> [Errno 32] Pipe error
  GONE    FEATURE_UNIT 4   volume ch1    GET CUR     -> handle went stale
  STALL   FEATURE_UNIT 4   volume ch1    GET RANGE   -> [Errno 32] Pipe error
  sanity: vendor 0x36 = 00, vendor 0x34 = 0x10  (so the transport itself is fine)
```

`wIndex`'s low byte is **3**, not 0, in every row: libusb will not route an interface-recipient
request to an interface we have not claimed, and we hold only IF3. Read on its own this table says
nothing about whether a class handler exists — which is exactly how I misread it before running the
two experiments above. The device survives all of it (`active image 0`, `GetAddressOfMain` =
`0x80010c88`, descriptors intact afterwards); the "GONE" rows are a stale WinUSB handle after an EP0
error, not a device reset.

---

## 3. New confirmed facts you did not have

**Flash protocol, working.** Vendor `0xA9` against the *running app*, sub-command in `wValue`,
index in `wIndex`, all big-endian: 0 `SetFlashAddress(4B, 0x80000000|off)`, 1 `WriteChunk(i, 64B)`
(8 per 512-byte page), 2 `CommitFlashPage`, 3 `ReadChunk(i)`, 4/5 `Get/SetUserPageCRC(img)`, 6
`Get/SetActiveImage(img)`, 7 `GetAddressOfMain`. Vendor `0xA7` = soft reset. `SetFlashAddress`
aligns **down** to 64 bytes. A full bank with per-page read-back takes 34–43 s on Windows. **[C]**

**The bootloader, dumped.** Because `0xA9` sub-command 3 reads flash and the decode ignores bit 18,
`0x0`–`0x4000` is readable: 16,384 bytes, stable across re-reads. It is **not** Apogee's. It is the
**stock Atmel UC3 USB DFU bootloader** — iProduct `AT32UC3A3 DFU 1.0.3` (UTF-16LE at `0x1caa`),
VID `0x03EB` / PID `0x2FF1`, `bcdDFUVersion 0x0101` = DFU 1.1. **[C]**

**There is no DFU rescue path for a bad app.** Two findings, both load-bearing for anyone writing
flash:
- DFU entry needs a **non-watchdog reset with SRAM preserved** *and* the key `0x4953504B`
  ("ISPK") in SRAM. `BLD Rd,bp` sets both C and Z from the tested bit, and cond3 `3` is `cs`, so
  **a watchdog reset clears the key and runs the app** — it does not fall into DFU. **[C, bytes +
  manual]**
- The launcher compares the bank's CRC with the value stored in the user page, moves to the other
  bank on mismatch, and `ICALL`s it **unconditionally**. So a CRC-wrong image never executes (A/B
  failover is real protection), but a **CRC-correct, functionally broken image just runs**. **[C]**

**The watchdog does not bite while idle.** `main()` = `FUN_80010C88` arms the WDT once
(`0x80010CD6` key `0x55001301`, `0x80010CEC` `0xAA001301`, CTRL `0x1301` → prescaler 19 → ≈9.11 s),
as you had. But a deliberately passive 16-minute watch (no USB access at all from the test, because
our own EP0 traffic would feed the watchdog and invalidate the measurement) saw zero re-enumeration
and `problem=0` throughout. **[C]** Caveat: `usbaudio2` was bound during that window, so I cannot
yet say whether *host EP0 traffic* or the firmware's own main loop is what feeds it. That is
deliverable §4.4.

**Free space.** `Image0` ends at file `0x180B8`; bank 0's app region runs to `0x20000`, and
`0x20000`, `0x22000`, `0x23000`, `0x23f00`, `0x1FF00` all read as all-`0xFF` with bank-1 code
starting at `0x24000`. Our flasher writes whatever pages a file contains inside the bank window and
then re-stores the device-computed user-page CRC, so adding code to the tail is CRC-safe for us.
**[C, live reads]**

**Tooling.** `pypcode`'s AVR32 decoder is not usable for verifying hand-written code: zero `BR{al}`
in a 90 KB image, every long branch rendered `ADD R0,R0,R0`, and `703c`/`70bc` decoded identically
although they must differ. We now have a minimal AVR32 assembler plus an independently written
disassembler, cross-checked on 17 real instructions, and an AVR32 toolchain installed. **[C]**

---

## 4. What to find now — ranked

### 4.1 Find the class handler — it exists — and table what it implements (highest value)

§2c settles that a class-request path exists and that four controls work — clock `SAM_FREQ`,
`FEATURE_UNIT 4` volume and mute, and `SELECTOR_UNIT 15` selector — because those are the four
`usbaudio2` actually sends, and all of them are answered. **What we still do not know is what the
handler implements beyond those four**, and that is the gap an iPad can fall into: iPadOS is free to
ask for `GET RANGE` on the clock, `CLOCK_VALID`, channel-count or terminal controls, or anything else
the descriptor advertises, at a point where Windows simply uses its cache.

- **Locate it.** The likeliest reason a reader of `FUN_80008432` concluded there was no class
  handling: ASF dispatches class requests through the *enabled interface's* `udi_api_t.setup`
  callback, not through one switch. Find the `udc_config` / interface API table, give its address,
  and give each entry's `setup` target. Then name the function that actually services UAC2 entity
  requests.
- **Table it.** For each `(entity id, control selector, GET CUR / GET RANGE / SET CUR)`: answered
  with what, or STALLed. Entities in the live descriptor: `CLOCK_SOURCE 1`, `FEATURE_UNIT 4`
  (playback), `SELECTOR_UNIT 15`, `FEATURE_UNIT 10` (capture), terminals 2/3/8/9/11/13.
- **Confirm the `wIndex` check** and which interface number the handler demands — that is what makes
  the interface-3 table above meaningless as evidence either way.

### 4.2 `SELECTOR_UNIT 15`: it works — now explain the gating

`SET CUR` on SU 15 demonstrably reaches `0x255C` (§2c experiment 2), so the iPad goal is no longer
blocked on a missing handler. The remaining questions are about edges:

- Which function services it, and does it route through `FUN_8000AA30(value-1, 3)` as I guessed in
  the earlier brief, or something else? What is that second argument?
- Does it validate the pin number, and does `GET CUR` return a **1-based** pin as ADC-2 requires? A
  host that reads back an out-of-range or 0-based value may refuse to switch even though `SET` works.
  This is the likeliest remaining way the iPad could still fail at input switching.

### 4.3 The sample-rate table

Partly answered from the host: the device accepts **44100 / 48000 / 88200 / 96000** and rejects
32000 / 22050, and it really runs at each accepted rate. This is physically consistent with the
descriptor — the device enumerates at **USB 2.0 high speed** (`bcdUSB 0x0200`, negotiated high) and
the iso endpoints are `wMaxPacketSize` 128 with `bInterval` 1, i.e. one packet per 125 µs microframe,
so 2 ch × 4-byte subslot = 8 B/frame gives a 128 kHz ceiling and 96 kHz needs 96 B per microframe.
**[C]**

What I still want from the firmware:

- The rate table in code, to confirm the list is exactly those four and not a subset of something
  larger that `usbaudio2` happens not to offer.
- The setter: does it genuinely reprogram the clock (PLL / codec over TWIM0), or accept the request
  and keep running at one rate? The wall-clock timing says it genuinely retunes, but I would like the
  code path named.
- Whether anything in the rate change depends on the vendor channel or on host-app state.

### 4.4 Every watchdog refresh site

List each WDT clear/refresh write and what calls it. The question to answer: **is the watchdog fed
by the main loop regardless of host traffic, or only from an EP0 path?** Our earlier working
hypothesis — the one that motivated the "put the watchdog to sleep for iPad" idea — was that EP0
idleness starves it. The 16-minute idle result above argues against that, but is not conclusive
(see the caveat). This is still **[H]**, and the user has explicitly asked that it stay labelled as
a hypothesis until settled.

### 4.5 iAP / MFi gating of audio

IF3 is the vendor/iAP interface (`class 0xff/0xf0`, 3 endpoints). Does any audio-enable path depend
on iAP identification completing, or on an MFi authentication coprocessor over TWIM0
(`0xFFFF2C00`)? If an Apple host must finish iAP before capture is usable, that is the real iPad
blocker and no amount of descriptor work fixes it. Look for the auth chip's I²C address and any
gate conditioned on it.

### 4.6 The string descriptor table

We measured that string indices 1, 2, 3 and 17–20 exist and every other index STALLs. Find the
table and the `GET_DESCRIPTOR(STRING)` handler, and say how many entries it has and where. We want
to give the selector and its three inputs readable names ("Internal Mic" / "External" /
"External +48 V") so hosts show them; that needs free indices and a handler that will serve them.

### 4.7 [P2] the encoder, which is now the next real firmware task

With [P1] done, the remaining goal is **removing the host-software dependency via an encoder
gesture**. Where is the encoder/knob decoded (vendor `0x29` is a 6-byte knob/state poll, `0x48` is
encoder-select), what gestures does the firmware already distinguish, and what does a long press or
double press do today? If there is an unused gesture and a free hook, input switching and gain
could be driven entirely from the device.

---

## 5. What not to spend time on

- The UAC2 class handler **for Windows**. Done differently; see §1.
- Any descriptor change, unless §4.3 or §4.6 forces one — then say so explicitly.
- The hook-placement question in general: if code does get written, it goes in the image's own free
  tail (`0x180B8`–`0x20000`), where the forward displacement is small and both banks relocate
  together, not at `0x20000`/`0x80040000`.
- Re-deriving the vendor protocol, the peripheral map, `main()`, or the mic input setter/getter —
  all still confirmed.
