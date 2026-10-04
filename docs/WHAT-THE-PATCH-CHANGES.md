# What the patch changes

Two things: the firmware's USB descriptor (340 → 284 bytes), and 82 bytes of code. Everything here
is rebuilt deterministically from your own stock images by `patch/patch_r9.py`.

## The USB descriptor

The ONE exposes **four** USB interfaces: `0` AudioControl, `1` AudioStreaming out (playback),
`2` AudioStreaming in (capture), `3` Apogee's own iAP/vendor interface. The descriptor describing
all of that shrinks from **340 to 284 bytes**; the slot in flash is 340 bytes hard, so it had to.

Stock → patched, every change:

| Where | Field | Stock | Patched | Why |
| --- | --- | --- | --- | --- |
| Config | `wTotalLength` | 340 | 284 | follows from the rest |
| IAD | `bInterfaceCount` | 4 | **3** | the audio function is interfaces 0–2. Stock swallowed the vendor interface into it. |
| AC header | `wTotalLength` | 174 | **111** | stock was wrong by 7 — it counted the interrupt endpoint descriptor, which the spec excludes. 167 were actually there. |
| Clock source 1 | `bmAttributes` | `0x01` internal **fixed** | `0x03` internal **programmable** | the device runs several sample rates; a fixed clock contradicts the rate control it advertises |
| Clock source 1 | — | **declared twice**, both with ID 1 | the duplicate is gone | unit IDs must be unique |
| Feature unit 4 (playback) | `bLength` | 10 | **18** | ADC-2 §4.7.2.8 says `6 + (channels+1)×4`. 10 describes a 0-channel unit on a stereo path. |
| Feature unit 4 | `bmaControls` | `0f000000` (master only) | master + L + R, each `0f000000` | mute and volume, per channel, as the hardware actually has |
| Feature unit 10 (mic) | `bLength` | 10 | **18** | same defect |
| Feature unit 10 | `bmaControls` | `04000000` — volume, host-readable | all **zero** | the firmware does not implement a mic volume control. Claiming one made hosts ask and get nothing. |
| Input terminal 9 (mic) | `bmChannelConfig` | `0x00000000` | `0x00000003` | FRONT_LEFT \| FRONT_RIGHT |
| Capture `AS_GENERAL` | `bmChannelConfig` | `0x00000004` FRONT_CENTER | `0x00000003` | one spatial bit for a two-channel stream is malformed. **This is what iPadOS refused.** |
| Output terminal 8 | `bSourceID` | 15 (the selector) | **10** (the mic feature unit) | the capture path no longer runs through a selector unit |
| Selector unit 15 | — | 3 pins, `iSelector` = string **21** | **removed** | iPadOS cannot build a capture path through a selector unit at all. String 21 does not exist on this device either. |
| Input terminals 11, 13 | — | duplicate mic terminals | **removed** | the three mic sources are one terminal; switching between them is the device's business, not the host's |
| Feature units 12, 14 | — | their feature units | **removed** | same |
| Endpoint `0x01` (playback) | `bmAttributes` | `0x0d` Synchronous | `0x09` **Adaptive** | the device does not lock to USB SOF |
| Endpoint `0x82` (capture) | `bmAttributes` | `0x0d` Synchronous | `0x05` **Asynchronous** | it runs on its own clock |
| Device | `bcdDevice` | 1.05 | 1.12 | so you can tell which firmware is running |

The two stored copies of the descriptor are identical except that the patched second copy carries
`bMaxPower` 6 instead of 5 — a deliberate marker, so you can tell from the host side which copy
the device actually served.

The single change that mattered most was removing the selector unit: **iPadOS will not build a
UAC2 capture path through one.** Most of the rest is compliance tidying that Windows and macOS
tolerated and the iPad did not.

Not all of it was tolerated, though. A device rolled back to factory firmware and plugged into
Windows 11 reports the audio function with **problem code 10, "this device cannot start"** — the
inbox `usbaudio2.sys` rejects the stock descriptor outright. That is measured on hardware, not
inferred, and it is the plainest statement of why this project exists.

## Apogee's own software still works

Changing the IAD moved interface 3 out of the audio function, which is the correction that makes
Windows expose it separately — and which could plausibly have hidden it from Apogee's own software
instead. It did not.

Observed on an M2 iPad Pro: **Apogee's iPad Maestro app, written for the Lightning era, still
drives the mixer and the device controls over USB-C after the patch.** Apple's MFi/iAP path to
interface 3 is untouched, so the vendor app keeps working alongside the class-compliant audio —
you are not trading one for the other.

What *is* out of reach on iOS is opening interface 3 yourself: third-party code gets no direct
access to it, which is why the knob had to learn to switch the mic source in firmware rather than
being driven from a host app. The MFi route Apogee uses needs their entitlement, not just the
descriptor.

## The code — 82 bytes

Two writes:

```
hook         4 bytes at 0x8000CBC8   `rcall 0x8000A208`  ->  `bral 0x8000C5D4`
trampoline  78 bytes at 0x8000C5D4   inside state 7's handler, which is dead code
```

Stock behaviour: a long press (held 105 main-loop passes) toggles output mute, in any focus state.
Apogee's own knowledge base documents it — hold the knob to mute and unmute the output.

After the patch, the long press checks which indicator currently has focus:

- **microphone focus** (Internal / External / External + 48 V) — advance the mic source one step,
  wrapping round;
- **instrument or output focus** — toggle mute, running Apogee's own code byte for byte.

So mute stays reachable from the panel: short-press to the instrument or speaker indicator, then
hold. That also keeps an escape route if host software leaves the output muted.

The trampoline is not a blob pasted in from somewhere. The patcher **lifts Apogee's own mute code
out of your image**, retargets its three `rcall`s for your bank, appends a jump back, and checks
the result against a SHA-256 of the exact bytes that were validated on hardware. If your image
differs, the hash fails and nothing is written.

### Why it is believed safe to overwrite state 7

The front panel is a state machine with a vtable of nine handlers at `0x8000C370`. Entry 7's
handler is 136 bytes long and **nothing can reach it**:

- the only 32-bit word in the whole 98,488-byte image pointing into that handler is the vtable
  entry itself, which the patch leaves alone;
- no 4-byte branch or call anywhere in the image resolves into the region — an algebraic scan of
  every even address finds zero hits — and no compact 2-byte branch in the neighbouring handlers
  does either;
- the constant 7 is never materialised inside the UI module, so nothing can store 7 into the focus
  variable: `mov Rd,0x7` appears 40 times in the image and 0 times in `0x8000C3B0..0x8000CD00`;
- all 36 instructions that address the focus variable at all are inside that same module.

These four arguments were chosen because none of them depends on a disassembler staying in sync
with the instruction stream — an earlier analysis pass desynced on the vtable (which is data) and
got this wrong, so the claim is made in ways that cannot fail the same way.

**What state 7 did** *(the code is established fact; what it was for is inference)*: its tick
handler paints bits 3/2/1/0 of a RAM byte onto four indicator ids; entering or leaving it blanks
all four and clears the mask; a press returns to state 6. That is an indicator-override display —
show an arbitrary combination of four lamps — and it is the fine-grained sibling of state 8,
"Identify", which lights everything. A diagnostic or annunciator display, most likely left over
from development. It is a *display*, not a producer: the status bits it would have shown are still
computed and still published to RAM by their one writer, so nothing host-visible is lost.

And if the region somehow were entered, the worst case is bounded: the focus value 7 passes both
comparisons, falls into the mic arm, advances the source once, and returns through a jump into a
correctly framed function. Wrong, not a crash — and that bound holds even if all four arguments
above were wrong.

58 of state 7's 136 bytes are still spare. 36 orphaned bytes after the hook are left exactly as
they were rather than filled with nops, so a diff against stock shows only what was deliberately
changed.

## Reproducible

`patch/patch_r9.py` builds the patched images from your stock images deterministically. Rebuilding
produces files byte-identical to the ones flashed and tested here, and it reports every byte it
changed — currently 488, with `bytes changed outside descriptor regions: 0` for the descriptor
rounds.

For the front-panel state machine in full, see
[onev2-ui-state-machine.md](onev2-ui-state-machine.md); for the descriptor against a compliant
reference, [descriptor-diff-vs-knowngood.md](descriptor-diff-vs-knowngood.md).
