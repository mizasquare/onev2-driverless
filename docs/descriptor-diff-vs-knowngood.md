# Apogee ONE (0c60:0017) UAC2 descriptor — diff vs. known-good, round 3

Date: 2026-10-02
Subject: Windows 11 `usbaudio2.sys` rejects config descriptor. Event ID 34
("A USB descriptor reported by device is not compliant with the specification,
or is not supported by the driver"), Device Manager Code 10, problem status
`0xC0440022`.

Every claim below is tagged **CONFIRMED** (read directly from the 332 bytes, or
quoted from an authoritative document/source I fetched and name) or
**HYPOTHESIS** (inference about what usbaudio2.sys actually does — I cannot read
the driver binary).

## Sources used as "known-good" and as normative references

1. **TinyUSB `uac2_headset`, UAC2 high-speed path** — the reference the task
   named. Files actually read:
   - `examples/device/uac2_headset/src/usb_descriptors.c` (master) — uses
     `TUD_AUDIO20_HEADSET_STEREO_DESCRIPTOR(5, EPNUM_AUDIO_OUT, EPNUM_AUDIO_IN | 0x80, EPNUM_AUDIO_INT | 0x80)`
   - `examples/device/uac2_headset/src/usb_descriptors.h` (master) — where
     `TUD_AUDIO20_HEADSET_STEREO_DESCRIPTOR` is **actually defined** (line 90).
     Note: it is *not* in `audio_device.h` or `usbd.h` as the task assumed; I
     checked those and 0.16.0/0.17.0/0.18.0 and it is not there.
   - `src/device/usbd.h` (master) — the `TUD_AUDIO20_DESC_*` primitives
   - `src/device/usbd.h` (0.16.0) — the older `TUD_AUDIO_DESC_*` primitives
     plus the full `TUD_AUDIO_MIC_ONE_CH/FOUR_CH/SPEAKER_MONO_FB` templates
   - `src/class/audio/audio.h`, `src/common/tusb_types.h` — constant values
   - `examples/device/uac2_headset/src/tusb_config.h` — channel/rate config
2. **Microsoft, "USB Audio 2.0 Drivers"**
   <https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/usb-2-0-audio-drivers>
   (page revision dated 2025-10-27). Quoted verbatim below where relevant.
3. **Linux kernel `include/linux/usb/audio-v2.h`** — independent implementation
   of the UAC2 descriptor layout, used as a second witness to the normative
   Feature Unit length formula.

Fetches that **failed** (stated for honesty, nothing was inferred from them):
`freelists.org` wdmaudiodev thread → HTTP 403; `xcore.com` thread → HTTP 406;
GitHub code-search API → requires auth. The `libusbgx` issue #24 and the
`marc.info` linux-usb thread were readable but contained only the
asynchronous-OUT-needs-feedback point already covered by the Microsoft doc.

---

## 1. Complete byte-exact parse of `usb-config-LIVE-after-R1.bin` (332 bytes)

The descriptor walk is self-consistent: summing every `bLength` from offset 0
lands exactly on 332 with no overrun and no gap. **CONFIRMED** (verified both by
hand and with a parser script).

```
off=  0 (0x000) len= 9  CONFIGURATION
off=  9 (0x009) len= 8  INTERFACE ASSOCIATION
off= 17 (0x011) len= 9  INTERFACE  itf=0 alt=0 nEP=1 cls=1/1/0x20   (AudioControl)
off= 26 (0x01a) len= 9  CS_INTERFACE  AC_HEADER
off= 35 (0x023) len= 8  CS_INTERFACE  CLOCK_SOURCE      id=1
off= 43 (0x02b) len=17  CS_INTERFACE  INPUT_TERMINAL    id=2  USB streaming
off= 60 (0x03c) len=12  CS_INTERFACE  OUTPUT_TERMINAL   id=3  Speaker
off= 72 (0x048) len=10  CS_INTERFACE  FEATURE_UNIT      id=4   <-- DEFECT
off= 82 (0x052) len=17  CS_INTERFACE  INPUT_TERMINAL    id=9  Microphone
off= 99 (0x063) len=10  CS_INTERFACE  FEATURE_UNIT      id=10  <-- DEFECT
off=109 (0x06d) len=17  CS_INTERFACE  INPUT_TERMINAL    id=11 Microphone
off=126 (0x07e) len=10  CS_INTERFACE  FEATURE_UNIT      id=12  <-- DEFECT
off=136 (0x088) len=17  CS_INTERFACE  INPUT_TERMINAL    id=13 Microphone
off=153 (0x099) len=10  CS_INTERFACE  FEATURE_UNIT      id=14  <-- DEFECT
off=163 (0x0a3) len=10  CS_INTERFACE  SELECTOR_UNIT     id=15
off=173 (0x0ad) len=12  CS_INTERFACE  OUTPUT_TERMINAL   id=8  USB streaming
off=185 (0x0b9) len= 7  ENDPOINT   0x83 attr=0x03 wMax=6   bInterval=12
off=192 (0x0c0) len= 9  INTERFACE  itf=1 alt=0 nEP=0 cls=1/2/0x20   (AS playback, zero-bw)
off=201 (0x0c9) len= 9  INTERFACE  itf=1 alt=1 nEP=1 cls=1/2/0x20
off=210 (0x0d2) len=16  CS_INTERFACE  AS_GENERAL   termLink=2
off=226 (0x0e2) len= 6  CS_INTERFACE  FORMAT_TYPE_I
off=232 (0x0e8) len= 7  ENDPOINT   0x01 attr=0x0d wMax=128 bInterval=1
off=239 (0x0ef) len= 8  CS_ENDPOINT   EP_GENERAL
off=247 (0x0f7) len= 9  INTERFACE  itf=2 alt=0 nEP=0 cls=1/2/0x20   (AS record, zero-bw)
off=256 (0x100) len= 9  INTERFACE  itf=2 alt=1 nEP=1 cls=1/2/0x20
off=265 (0x109) len=16  CS_INTERFACE  AS_GENERAL   termLink=8
off=281 (0x119) len= 6  CS_INTERFACE  FORMAT_TYPE_I
off=287 (0x11f) len= 7  ENDPOINT   0x82 attr=0x0d wMax=128 bInterval=1
off=294 (0x126) len= 8  CS_ENDPOINT   EP_GENERAL
off=302 (0x12e) len= 9  INTERFACE  itf=3 alt=0 nEP=3 cls=255/240/0x00 (vendor)
off=311 (0x137) len= 7  ENDPOINT   0x04 attr=0x02 wMax=512 bInterval=0
off=318 (0x13e) len= 7  ENDPOINT   0x85 attr=0x02 wMax=512 bInterval=0
off=325 (0x145) len= 7  ENDPOINT   0x86 attr=0x03 wMax=1   bInterval=4
                        = 332 total
```

### 1.1 Field-by-field decode with absolute offsets

**CONFIGURATION @ 0** (`09 02 4c 01 04 01 00 c0 05`)

| off | field | value |
|---|---|---|
| 0 | bLength | 9 |
| 1 | bDescriptorType | 0x02 |
| 2-3 | wTotalLength | 0x014C = **332** (consistent) |
| 4 | bNumInterfaces | 4 |
| 5 | bConfigurationValue | 1 |
| 6 | iConfiguration | 0 |
| 7 | bmAttributes | 0xC0 (self-powered, no remote wakeup) |
| 8 | bMaxPower | 5 → 10 mA |

**INTERFACE ASSOCIATION @ 9** (`08 0b 00 03 01 00 20 00`)

| off | field | value |
|---|---|---|
| 9 | bLength | 8 |
| 10 | bDescriptorType | 0x0B |
| 11 | bFirstInterface | 0 |
| 12 | bInterfaceCount | **3** (vendor itf 3 correctly excluded) |
| 13 | bFunctionClass | 0x01 AUDIO |
| 14 | bFunctionSubClass | 0x00 UNDEFINED |
| 15 | bFunctionProtocol | 0x20 AF_VERSION_02_00 |
| 16 | iFunction | 0 |

Byte-identical to `TUD_AUDIO20_DESC_IAD` output
(`..., TUSB_CLASS_AUDIO, AUDIO_FUNCTION_SUBCLASS_UNDEFINED, AUDIO_FUNC_PROTOCOL_CODE_V2, _stridx`).
**CONFIRMED correct.**

**STD AC INTERFACE @ 17** (`09 04 00 00 01 01 01 20 00`)
itf=0, alt=0, nEP=1, class/sub/proto = 1/1/0x20, iInterface=0. Matches
`TUD_AUDIO20_DESC_STD_AC(..., _nEPs 0x01, ...)` from the known-good headset.
**CONFIRMED correct.**

**CS AC HEADER @ 26** (`09 24 01 00 02 04 9f 00 01`)

| off | field | value |
|---|---|---|
| 26 | bLength | 9 |
| 27 | bDescriptorType | 0x24 CS_INTERFACE |
| 28 | bDescriptorSubtype | 0x01 HEADER |
| 29-30 | bcdADC | 0x0200 |
| 31 | bCategory | 0x04 = HEADSET (same as known-good `AUDIO20_FUNC_HEADSET`) |
| 32-33 | wTotalLength | 0x009F = **159** |
| 34 | bmControls | 0x01 (Latency Control, read-only) |

wTotalLength check: 26 + 159 = 185 = offset of the AC interrupt endpoint.
Sum of the class-specific AC descriptors = 9+8+17+12+10+17+10+17+10+17+10+10+12
= 159. **CONFIRMED consistent.**

**CLOCK_SOURCE @ 35** (`08 24 0a 01 01 07 00 00`)

| off | field | value |
|---|---|---|
| 38 | bClockID | 1 |
| 39 | bmAttributes | **0x01** = Internal **fixed** clock; D2 (synced to SOF) = 0 |
| 40 | bmControls | 0x07 = freq control **host-programmable** (D1:0=11b) + validity read-only (D3:2=01b) |
| 41 | bAssocTerminal | 0 |
| 42 | iClockSource | 0 |

Exactly one clock source in the whole descriptor. **CONFIRMED.** See defect #3.

**INPUT_TERMINAL id=2 @ 43** (`11 24 02 02 01 01 00 01 02 03 00 00 00 00 00 00 00`)

| off | field | value |
|---|---|---|
| 46 | bTerminalID | 2 |
| 47-48 | wTerminalType | 0x0101 USB Streaming |
| 49 | bAssocTerminal | 0 |
| 50 | bCSourceID | 1 |
| 51 | bNrChannels | 2 |
| 52-55 | bmChannelConfig | 0x00000003 (FL+FR) — 2 bits for 2 channels, consistent |
| 56 | iChannelNames | 0 |
| 57-58 | bmControls | 0x0000 |
| 59 | iTerminal | 0 |

**OUTPUT_TERMINAL id=3 @ 60** (`0c 24 03 03 01 03 00 04 01 00 00 00`)

| off | field | value |
|---|---|---|
| 63 | bTerminalID | 3 |
| 64-65 | wTerminalType | 0x0301 Speaker |
| 66 | bAssocTerminal | 0 |
| 67 | bSourceID | 4 (FU 4) |
| 68 | bCSourceID | 1 |
| 69-70 | bmControls | 0x0000 |
| 71 | iTerminal | 0 |

**FEATURE_UNIT id=4 @ 72** (`0a 24 06 04 02 0f 00 00 00 00`)

| off | field | value |
|---|---|---|
| 72 | **bLength** | **10** |
| 75 | bUnitID | 4 |
| 76 | bSourceID | 2 (IT 2, **bNrChannels = 2**) |
| 77-80 | bmaControls[0] (master) | 0x0000000F = mute RW + volume RW |
| 81 | iFeature | 0 |

Only **one** bmaControls entry. See defect #1.

**INPUT_TERMINAL id=9 @ 82** (`11 24 02 09 01 02 00 01 02 00 00 00 00 00 00 00 12`)

| off | field | value |
|---|---|---|
| 85 | bTerminalID | 9 |
| 86-87 | wTerminalType | 0x0201 Microphone |
| 88 | bAssocTerminal | 0 |
| 89 | bCSourceID | 1 |
| 90 | bNrChannels | 2 |
| 91-94 | bmChannelConfig | 0x00000000 (non-predefined) |
| 95 | iChannelNames | 0 |
| 96-97 | bmControls | 0x0000 |
| 98 | iTerminal | 18 |

**FEATURE_UNIT id=10 @ 99** (`0a 24 06 0a 09 04 00 00 00 12`)
bLength=10, bUnitID=10 (@102), bSourceID=9 (@103), bmaControls[0]=0x00000004
(@104-107, volume **read-only**, no mute), iFeature=18 (@108).

**INPUT_TERMINAL id=11 @ 109** — identical shape to id=9.
bTerminalID=11 (@112), wTerminalType=0x0201 (@113-114), bCSourceID=1 (@116),
bNrChannels=2 (@117), bmChannelConfig=0x00000000 (@118-121),
iChannelNames=0 (@122), bmControls=0x0000 (@123-124), iTerminal=19 (@125).

**FEATURE_UNIT id=12 @ 126** — bLength=10, bUnitID=12 (@129), bSourceID=11
(@130), bmaControls[0]=0x00000004 (@131-134), iFeature=19 (@135).

**INPUT_TERMINAL id=13 @ 136** — bTerminalID=13 (@139),
wTerminalType=0x0201 (@140-141), bCSourceID=1 (@143), bNrChannels=2 (@144),
bmChannelConfig=0x00000000 (@145-148), iChannelNames=0 (@149),
bmControls=0x0000 (@150-151), iTerminal=20 (@152).

**FEATURE_UNIT id=14 @ 153** — bLength=10, bUnitID=14 (@156), bSourceID=13
(@157), bmaControls[0]=0x00000004 (@158-161), iFeature=20 (@162).

**SELECTOR_UNIT id=15 @ 163** (`0a 24 05 0f 03 0a 0c 0e 03 15`)

| off | field | value |
|---|---|---|
| 163 | bLength | 10 = 7 + bNrInPins(3) — **correct** |
| 166 | bUnitID | 15 |
| 167 | bNrInPins | 3 |
| 168-170 | baSourceID[1..3] | 10, 12, 14 |
| 171 | bmControls | 0x03 Selector Control host-programmable |
| 172 | iSelector | 21 |

**OUTPUT_TERMINAL id=8 @ 173** (`0c 24 03 08 01 01 00 0f 01 00 00 00`)
bTerminalID=8 (@176), wTerminalType=0x0101 USB Streaming (@177-178),
bAssocTerminal=0 (@179), bSourceID=15 (@180), bCSourceID=1 (@181),
bmControls=0x0000 (@182-183), iTerminal=0 (@184).

**STD AC INTERRUPT ENDPOINT @ 185** (`07 05 83 03 06 00 0c`)
bEndpointAddress=0x83 (@187), bmAttributes=0x03 interrupt (@188),
wMaxPacketSize=6 (@189-190), bInterval=**12** (@191) → 2^11 = 2048 microframes
= 256 ms at high speed.

**STD AS INTERFACE itf1 alt0 @ 192** — nEP=0 (@196), cls 1/2/0x20 (@197-199).
Zero-bandwidth alt 0. **CONFIRMED correct per the Microsoft doc requirement.**

**STD AS INTERFACE itf1 alt1 @ 201** — alt=1 (@204), nEP=1 (@205),
cls 1/2/0x20 (@206-208).

**CS AS_GENERAL @ 210** (`10 24 01 02 00 01 01 00 00 00 02 03 00 00 00 00`)

| off | field | value |
|---|---|---|
| 213 | bTerminalLink | 2 → IT 2, USB Streaming. Valid. |
| 214 | bmControls | 0x00 |
| 215 | bFormatType | 1 |
| 216-219 | bmFormats | 0x00000001 PCM — exactly one bit |
| 220 | bNrChannels | 2 |
| 221-224 | bmChannelConfig | 0x00000003 (FL+FR) — 2 bits, **consistent** |
| 225 | iChannelNames | 0 |

**FORMAT_TYPE_I @ 226** (`06 24 02 01 04 18`)
bFormatType=1 (@229) — matches AS_GENERAL bFormatType. bSubslotSize=4 (@230),
bBitResolution=24 (@231).

**STD ISO ENDPOINT (OUT) @ 232** (`07 05 01 0d 80 00 01`)

| off | field | value |
|---|---|---|
| 234 | bEndpointAddress | 0x01 (OUT, sink) |
| 235 | bmAttributes | **0x0D** = iso + **Synchronous** (D3:2=11b) + data |
| 236-237 | wMaxPacketSize | 128 |
| 238 | bInterval | 1 (every microframe, 125 us) |

No feedback endpoint in this alt setting (nEP=1).

**CS ISO EP (EP_GENERAL) @ 239** (`08 25 01 00 00 01 08 00`)
bmAttributes=0x00 (@242), bmControls=0x00 (@243), bLockDelayUnits=1 ms (@244),
wLockDelay=8 (@245-246).

**STD AS INTERFACE itf2 alt0 @ 247** — nEP=0 (@251). Zero-bandwidth. Correct.

**STD AS INTERFACE itf2 alt1 @ 256** — alt=1 (@259), nEP=1 (@260).

**CS AS_GENERAL @ 265** (`10 24 01 08 00 01 01 00 00 00 02 04 00 00 00 00`)

| off | field | value |
|---|---|---|
| 268 | bTerminalLink | 8 → OT 8, USB Streaming. Valid. |
| 269 | bmControls | 0x00 |
| 270 | bFormatType | 1 |
| 271-274 | bmFormats | 0x00000001 PCM — exactly one bit |
| 275 | bNrChannels | **2** |
| 276-279 | bmChannelConfig | **0x00000004 (FC only — ONE bit)** |
| 280 | iChannelNames | **0** |

See defect #2.

**FORMAT_TYPE_I @ 281** — bFormatType=1 (@284), bSubslotSize=4 (@285),
bBitResolution=24 (@286).

**STD ISO ENDPOINT (IN) @ 287** (`07 05 82 0d 80 00 01`)
bEndpointAddress=0x82 (@289), bmAttributes=**0x0D** Synchronous (@290),
wMaxPacketSize=128 (@291-292), bInterval=1 (@293).

**CS ISO EP @ 294** — bmAttributes=0x00 (@297), bmControls=0x00 (@298),
bLockDelayUnits=1 (@299), wLockDelay=8 (@300-301).

**VENDOR INTERFACE itf3 @ 302** — nEP=3 (@306), cls 255/240/0x00 (@307-309),
iInterface=17 (@310). Endpoints 0x04 bulk 512 (@311), 0x85 bulk 512 (@318),
0x86 interrupt 1 byte bInterval=4 (@325). Outside the audio function; not the
driver's concern.

---

## 2. The known-good reference, decoded

From `usb_descriptors.h` line 90 (`TUD_AUDIO20_HEADSET_STEREO_DESCRIPTOR`) plus
the `TUD_AUDIO20_DESC_*` primitives in `src/device/usbd.h` and the constants in
`audio.h` / `tusb_types.h`. All values below are **CONFIRMED** by reading those
files.

| Element | Known-good value | Ours | Same? |
|---|---|---|---|
| IAD class/sub/proto | 0x01 / 0x00 / 0x20 | 0x01 / 0x00 / 0x20 | yes |
| AC interface nEP | 1 | 1 | yes |
| AC header bCategory | `AUDIO20_FUNC_HEADSET` = 0x04 | 0x04 | yes |
| AC header bmControls | `..._CTRL_LATENCY_POS` = **0** | 0x01 | differs (benign) |
| **Clock bmAttributes** | **3** (internal **programmable**) | **0x01** (internal **fixed**) | **differs** |
| Clock bmControls | 7 | 0x07 | yes |
| IT (2-ch) bmChannelConfig | `NON_PREDEFINED` = 0x00000000 | 0x00000003 | differs (both OK) |
| **FU bLength (2-ch cluster)** | `FEATURE_UNIT_LEN(2)` = **18** | **10** | **differs** |
| FU bmaControls entries | **3** (master + ch1 + ch2) | **1** (master only) | **differs** |
| FU bmaControls value | (RW<<0)\|(RW<<2) = **0x0F** | 0x0F (spk) / 0x04 (mic) | spk same |
| AC int EP bmAttributes / wMax | `TUSB_XFER_INTERRUPT` 0x03 / 6 | 0x03 / 6 | yes |
| AC int EP bInterval | 1 | 12 | differs (both legal) |
| AS interface cls/sub/proto | 1 / 2 / 0x20 | 1 / 2 / 0x20 | yes |
| AS alt 0 endpoints | 0 | 0 | yes |
| AS bmFormats | PCM, one bit | 0x00000001 | yes |
| AS bmChannelConfig | 0x00000000 both directions | 0x03 (play) / **0x04** (rec) | **rec differs** |
| **OUT iso bmAttributes** | iso\|**ADAPTIVE**\|data = **0x09** | **0x0D** (Synchronous) | **differs** |
| **IN iso bmAttributes** | iso\|**ASYNCHRONOUS**\|data = **0x05** | **0x0D** (Synchronous) | **differs** |
| iso bInterval | 1 | 1 | yes |
| Feedback endpoint | none (OUT is Adaptive) | none | yes |
| CS iso EP bLength | 8 | 8 | yes |

Endpoint size formula in the known-good (`usbd.h` master, line 790):

```c
#define TUD_AUDIO_EP_SIZE(_is_highspeed, _maxFrequency, _nBytesPerSample, _nChannels) \
    (((((_maxFrequency) + ((_is_highspeed) ? 7999 : 999)) / ((_is_highspeed) ? 8000 : 1000)) + 1) * (_nBytesPerSample) * (_nChannels))
```

For our worst case (96 kHz, 4 bytes/sample, 2 channels, high speed):
`(ceil(96000/8000) + 1) * 4 * 2 = (12+1)*8 = 104`. Our 128 >= 104.
**CONFIRMED: wMaxPacketSize=128 with bInterval=1 is adequate up to 96 kHz and is
not a defect.** (It would be insufficient for 192 kHz, which needs 200.)

---

## 3. Difference analysis, ranked

### DEFECT #1 — HIGH — Feature Unit `bLength` = 10, must be 18 (4 occurrences)

**CONFIRMED (bytes):** all four Feature Units have `bLength = 0x0A = 10`, i.e. a
single 4-byte `bmaControls` entry, while every one of their source entities
declares `bNrChannels = 2`:

| FU | offset of bLength | bSourceID | source entity | source bNrChannels |
|---|---|---|---|---|
| id=4 | **72** | 2 | IT 2 @43 | 2 (byte @51) |
| id=10 | **99** | 9 | IT 9 @82 | 2 (byte @90) |
| id=12 | **126** | 11 | IT 11 @109 | 2 (byte @117) |
| id=14 | **153** | 13 | IT 13 @136 | 2 (byte @144) |

**CONFIRMED (normative formula), three independent witnesses:**

- ADC-2 section 4.7.2.8 requires `bLength = 6 + (ch + 1) * 4` where `ch` is the
  number of logical channels in the Feature Unit's **input** cluster, and
  `bmaControls()` is a `(ch+1)`-element array of 4-byte bitmaps:
  `bmaControls[0]` = master, `bmaControls[1..ch]` = per-channel.
- **Linux kernel**, `include/linux/usb/audio-v2.h`, under the comment
  `/* 4.7.2.8 Feature Unit Descriptor */`:
  ```c
  #define UAC2_DT_FEATURE_UNIT_SIZE(ch)		(6 + ((ch) + 1) * 4)
  ...
  #define DECLARE_UAC2_FEATURE_UNIT_DESCRIPTOR(ch)  ... __le32 bmaControls[ch + 1]; ...
  ```
- **TinyUSB**, `src/device/usbd.h` (master):
  ```c
  #define TUD_AUDIO20_DESC_FEATURE_UNIT_LEN(_nchannels) (6 + ((_nchannels) + 1) * 4)
  ```
  and in 0.16.0 explicitly:
  ```c
  #define TUD_AUDIO_DESC_FEATURE_UNIT_ONE_CHANNEL_LEN 6+(1+1)*4      /* = 14 */
  #define TUD_AUDIO_DESC_FEATURE_UNIT_TWO_CHANNEL_LEN (6+(2+1)*4)    /* = 18 */
  ```
  The known-good headset's 2-channel speaker Feature Unit uses
  `TUD_AUDIO20_DESC_FEATURE_UNIT_LEN(2)` = **18** and passes three bitmaps
  (`_ctrlch0master, _ctrlch1, _ctrlch2`). **TinyUSB never emits bLength 10.**

Solving the formula for our value: `10 = 6 + (ch+1)*4` → **ch = 0**. So our
descriptor tells the host "this Feature Unit's input cluster has zero channels"
while the terminal feeding it says two. Inverting it the way Linux does
(`(bLength - 6)/4 - 1`) gives the same answer: 0 channels.

**Why the earlier "ruled out" verdict was wrong.** The Microsoft sentence that
was used to dismiss this reads, verbatim:

> "If a feature unit implements single channel controls and a primary control
> for Mute or Volume, then the driver uses the single channel controls and
> ignores the primary control."

That sentence sits in the page's **"Class requests and interrupt data messages →
Feature unit"** section, alongside statements about `GET RANGE`/`SET CUR`
behaviour. It describes which *control* the driver drives at **runtime when both
kinds are present**. It says nothing about `bLength`, and it does not authorise a
`bmaControls` array shorter than the spec formula. In the page's **"Descriptors"**
section Microsoft instead says:

> "The driver supports all descriptor types defined in ADC-2, section 4."

— i.e. it expects ADC-2 section 4 layouts, which is exactly the formula above. I
am therefore re-raising this as the **#1 candidate**, with the distinction made
explicit rather than relying on the earlier reading.

**HYPOTHESIS (why this produces exactly Event ID 34):** a parser that computes
the per-channel control offsets as `6 + 4*n` for `n = 0..bNrChannels` will, for a
2-channel cluster, read 8 bytes past the end of a 10-byte descriptor — landing
inside the *next* descriptor. A length-validating parser detects
`bLength != 6+(ch+1)*4` and fails the whole configuration with
"descriptor ... is not compliant with the specification". This is the only
**hard, formula-level** length violation anywhere in the 332 bytes; every other
finding below is legal-but-unusual or a semantic inconsistency. That is why it
ranks first.

**Exact byte changes.** Grows the descriptor by 4 x 8 = **32 bytes** (332 → 364).
Apply from the highest offset downwards so earlier edits do not shift later ones.
Offsets below are **pre-patch**.

| # | offset(s) | from | to |
|---|---|---|---|
| 1 | 153 | `0a` | `12` |
| 2 | insert after 161 (before iFeature @162) | — | `04 00 00 00 04 00 00 00` |
| 3 | 126 | `0a` | `12` |
| 4 | insert after 134 (before iFeature @135) | — | `04 00 00 00 04 00 00 00` |
| 5 | 99 | `0a` | `12` |
| 6 | insert after 107 (before iFeature @108) | — | `04 00 00 00 04 00 00 00` |
| 7 | 72 | `0a` | `12` |
| 8 | insert after 80 (before iFeature @81) | — | `0f 00 00 00 0f 00 00 00` |
| 9 | 32-33 (AC wTotalLength) | `9f 00` | `bf 00` (159 → **191**) |
| 10 | 2-3 (config wTotalLength) | `4c 01` | `6c 01` (332 → **364**) |

Per-channel bitmaps are set equal to the existing master value so the advertised
capability does not change. (For the mic units `0x04` = volume read-only; if you
also want a *writable* input gain, use `0f 00 00 00` for all three entries —
that is a separate functional change, not part of the compliance fix.)

**If flash layout cannot grow**, there is a shrinking variant that is also a
clean bisection toward the known-good topology: delete the three mic Feature
Units (FU 10 @99, FU 12 @126, FU 14 @153 — 30 bytes) and repoint the Selector
Unit directly at the input terminals by changing offsets 168, 169, 170 from
`0a 0c 0e` to `09 0b 0d`; then grow only FU 4 by 8 bytes. Net **-22 bytes**
(332 → 310), AC wTotalLength = 159 - 30 + 8 = **137** (`89 00` at 32-33),
config wTotalLength = **310** (`36 01` at 2-3). This costs the (currently
read-only, therefore useless) mic volume controls.

---

### DEFECT #2 — HIGH/MEDIUM — record AS interface declares 2 channels but a one-bit channel config, and it contradicts the upstream cluster

**CONFIRMED (bytes):** AS_GENERAL for interface 2 (record) at offset 265 has
`bNrChannels = 2` (byte @**275**) and `bmChannelConfig = 0x00000004` (bytes
@**276-279**), i.e. **Front Center only — exactly one spatial location for two
logical channels** — with `iChannelNames = 0` (byte @**280**), so the second
channel has neither a spatial location nor a name.

Two distinct problems in one field:

1. **Internal inconsistency.** An ADC-2 audio channel cluster is described by
   `bNrChannels` + `bmChannelConfig` + `iChannelNames`: channels occupying
   predefined spatial locations are the bits of `bmChannelConfig`, and any
   remaining channels are named from `iChannelNames` onward. Here
   popcount(0x04) = 1, plus 0 named channels, = 1 — but `bNrChannels` says 2.
2. **Mismatch with the terminal it links to.** `bTerminalLink = 8` (@268) → OT 8
   @173, whose `bSourceID = 15` (SU 15) ← FU 10/12/14 ← IT 9/11/13, all of which
   declare `bmChannelConfig = 0x00000000` (bytes @91-94, @118-121, @145-148).
   So the stream's cluster is described one way at the terminal and a different
   way at the AS interface.

The playback side does **not** have this problem: AS interface 1 has
`bNrChannels = 2` (@220) and `bmChannelConfig = 0x00000003` (@221-224, FL+FR,
two bits) and its linked IT 2 declares the same 0x00000003 (@52-55).
**CONFIRMED self-consistent.**

**Known-good comparison:** `TUD_AUDIO20_DESC_CS_AS_INT` is always invoked with
`/*_channelcfg*/ AUDIO20_CHANNEL_CONFIG_NON_PREDEFINED`, and
`AUDIO20_CHANNEL_CONFIG_NON_PREDEFINED = 0x00000000` (**CONFIRMED** in
`audio.h`). Zero bits set is explicitly the "all channels non-predefined" case
and is legal for any `bNrChannels`; **one** bit set for two channels is not.

Note this also explains why the mic *input terminals* having
`bmChannelConfig = 0x00000000` with `bNrChannels = 2` is **not** a defect:
TinyUSB's `TUD_AUDIO_MIC_FOUR_CH_DESCRIPTOR` does exactly that
(`_nchannelslogical 0x04`, `_channelcfg AUDIO_CHANNEL_CONFIG_NON_PREDEFINED`)
and that example works on Windows. **CONFIRMED not the defect.**

**HYPOTHESIS:** Windows maps `bmChannelConfig` onto a KSAUDIO channel mask. A
2-channel stream whose mask contains only `SPEAKER_FRONT_CENTER` is an
inconsistent (count, mask) pair. Whether `usbaudio2.sys` rejects the descriptor
outright or merely builds a broken endpoint I cannot confirm.

**Exact byte change — one byte, no length impact (cheapest possible test):**

| offset | from | to | effect |
|---|---|---|---|
| **276** | `04` | `00` | bmChannelConfig 0x00000004 → 0x00000000 (matches known-good and the upstream terminals) |

Alternative, if you prefer a stereo spatial mask: set offset 276 = `03`
(FL+FR), and for full consistency also set the three mic input terminals'
`bmChannelConfig` low bytes at offsets **91**, **118**, **145** from `00` to
`03`. Matching the known-good (`0x00000000`) is the lower-risk choice.

---

### DEFECT #3 — MEDIUM — clock source typed "internal fixed" while advertising a host-programmable frequency control

**CONFIRMED (bytes):** offset **39** = `0x01`. Per ADC-2 section 4.7.2.1
Table 4-6, `bmAttributes` D1:D0 is the Clock Type (00 = External, 01 = Internal
**fixed**, 10 = Internal variable, 11 = Internal **programmable**) and D2 = 1
when the clock is synchronised to SOF. So we declare internal **fixed**, not
SOF-synced.

Meanwhile offset **40** = `0x07`: `bmControls` D1:D0 = 11b = Sampling Frequency
Control **host-programmable** (SET CUR supported). A *fixed* clock that accepts
`SET CUR` is self-contradictory, and the Apogee ONE does support several rates.

**CONFIRMED (known-good):** the headset uses `/*_attr*/ 3` — internal
**programmable** — with the identical `/*_ctrl*/ 7`. Our bmControls already
matches; only the clock type is wrong.

**CONFIRMED (Microsoft doc):**

> "A Clock Source Entity that implements one single fixed frequency only doesn't
> need to implement Sampling Frequency Control SET CUR. It implements GET CUR,
> which returns the fixed frequency. It also implements GET RANGE, which reports
> one single discrete frequency."

and

> "At a minimum, a Clock Source Entity must implement Sampling Frequency Control
> GET RANGE and GET CUR requests (ADC-2 5.2.5.1.1) in compatible USB Audio 2.0
> hardware."

Good news: our `bmControls = 0x07` also sets D3:D2 = 01b, i.e. **Clock Validity
Control present (read-only)**, which ADC-2 section 5.2.5.1.2 requires and which
is a known tripwire for UAC2 devices on Windows. **CONFIRMED present — not a
defect.**

**Exact byte change — one byte, no length impact:**

| offset | from | to |
|---|---|---|
| **39** | `01` | `03` (internal programmable clock) |

**HYPOTHESIS:** on its own this is more likely to break sample-rate *negotiation*
(`SET CUR` refused against a clock typed fixed) than to cause the descriptor
parse to fail. Rated medium rather than high for that reason — but it is a
one-byte change that moves us onto the known-good value, so it costs nothing to
include.

---

### DEFECT #4 — MEDIUM — iso endpoints declare Synchronous while the clock is not SOF-locked

**CONFIRMED (bytes):** offset **235** (OUT, EP 0x01) = `0x0D` and offset **290**
(IN, EP 0x82) = `0x0D`. Decoding USB 2.0 Table 9-13: bits 1:0 = 01 Isochronous,
bits 3:2 = **11 = Synchronous**, bits 5:4 = 00 Data endpoint.

"Synchronous" asserts that the endpoint's data rate is locked to the bus SOF
clock. But the clock source at offset 39 has D2 (synchronised to SOF) **clear**
(`0x01`). The device therefore simultaneously claims "my clock is internal and
not SOF-derived" and "my endpoints are SOF-synchronous". This is the untested
hypothesis from the task brief, and it is a genuine contradiction.

**CONFIRMED (known-good) — and the answer to "does TinyUSB set the SOF bit?":
no, it does not, and it avoids the contradiction by not declaring Synchronous
endpoints at all.** The headset uses, verbatim:

- OUT (sink): `TUSB_XFER_ISOCHRONOUS | TUSB_ISO_EP_ATT_ADAPTIVE | TUSB_ISO_EP_ATT_DATA`
- IN (source): `TUSB_XFER_ISOCHRONOUS | TUSB_ISO_EP_ATT_ASYNCHRONOUS | TUSB_ISO_EP_ATT_DATA`

With `TUSB_ISO_EP_ATT_ASYNCHRONOUS = 0x04`, `TUSB_ISO_EP_ATT_ADAPTIVE = 0x08`,
`TUSB_ISO_EP_ATT_SYNCHRONOUS = 0x0C`, `TUSB_ISO_EP_ATT_DATA = 0x00`
(**CONFIRMED** in `tusb_types.h`), that is **0x09 for OUT** and **0x05 for IN**,
paired with clock `bmAttributes = 3` (internal programmable, D2 clear) — a
self-consistent "device has its own clock" design.

**CONFIRMED (Microsoft doc):** all three sync types are supported —

> "The driver supports the following endpoint synchronization types (USB-2
> 5.12.4.1): Asynchronous IN and OUT; Synchronous IN and OUT; Adaptive IN and
> OUT"

— so Synchronous is not *rejected on sight*. And on feedback:

> "For the asynchronous OUT case, the driver supports explicit feedback only. A
> feedback endpoint must be implemented in the respective alternate setting of
> the AS interface. The driver doesn't support implicit feedback."

**Answers the "is a feedback endpoint required?" question: only for
ASYNCHRONOUS OUT.** Our OUT is currently Synchronous, and the known-good's OUT
is Adaptive; **neither requires a feedback endpoint**. Its absence is therefore
**CONFIRMED not a defect as the descriptor currently stands.**

**Exact byte changes — two bytes, no length impact:**

| offset | from | to | meaning |
|---|---|---|---|
| **235** | `0d` | `09` | OUT endpoint → Adaptive (known-good value) |
| **290** | `0d` | `05` | IN endpoint → Asynchronous (known-good value) |

**Critical warning:** do **not** set offset 235 to `05` (Asynchronous OUT)
unless you also add a feedback IN endpoint to interface 1 alt 1 and bump
`bNumEndpoints` at offset 205 from 1 to 2 — the Microsoft text above makes
explicit feedback mandatory in that case. `09` (Adaptive) needs no feedback
endpoint and is what the known-good uses.

The alternative repair direction — keep `0x0D` and set the clock's SOF bit
(offset 39 → `0x05` = internal fixed + SOF-synced, or `0x07` = programmable +
SOF-synced) — makes the descriptor self-consistent but asserts the hardware
genuinely slaves its audio clock to USB SOF. For an Apogee ONE with its own
crystal that is almost certainly false, so prefer the Adaptive/Asynchronous
direction.

---

### DEFECT #5 — LOW — mic Feature Units expose volume as read-only, no mute

**CONFIRMED (bytes):** `bmaControls[0]` = `0x00000004` at offsets **104-107**
(FU 10), **131-134** (FU 12), **158-161** (FU 14). Decoding ADC-2 section 4.7.2.8
Table 4-13: D1:D0 = Mute Control = 00 (not present), D3:D2 = Volume Control =
01 (present, **read-only**).

Legal, so not a rejection cause. But the known-good uses
`(AUDIO20_CTRL_RW << MUTE_POS) | (AUDIO20_CTRL_RW << VOLUME_POS)` =
`(0x03 << 0) | (0x03 << 2)` = **0x0F** (**CONFIRMED**: `AUDIO20_CTRL_RW = 0x03`,
`..._MUTE_POS = 0`, `..._VOLUME_POS = 2`). Our playback FU 4 already uses
`0x0000000F` (offsets 77-80) — an exact match with known-good. The mic units
will present an input gain slider Windows cannot move.

Fix (optional, functional not compliance): offsets 104, 131, 158 → `0f`. Best
done together with defect #1, which is where the per-channel entries get added.

---

### DEFECT #6 — LOW — AC interrupt endpoint `bInterval` = 12 (256 ms)

**CONFIRMED (bytes):** offset **191** = `0x0C`. At high speed the interrupt
interval is 2^(bInterval-1) microframes = 2^11 = 2048 x 125 us = **256 ms**.
Legal (high-speed interrupt allows 1..16). The known-good uses
`TUD_AUDIO20_DESC_STD_AC_INT_EP(_ep, /*_interval*/ 0x01)` = **1**.
`bmAttributes` (0x03) and `wMaxPacketSize` (6) both match known-good exactly
(`TUSB_XFER_INTERRUPT, U16_TO_U8S_LE(6)` — **CONFIRMED**).

Only affects how quickly mute/volume/connector change notifications arrive.
Optional fix: offset 191 → `01` (or `04` for 1 ms).

---

## 4. Explicitly checked and found CORRECT (ruled out)

All **CONFIRMED** by reading the bytes and/or the cited document.

| Item | Evidence |
|---|---|
| `wTotalLength` = 332 | descriptor walk lands exactly on 332 |
| AC `wTotalLength` = 159 | 26 + 159 = 185 = AC interrupt EP offset; the 13 class-specific AC descriptors sum to 159 |
| Exactly one Clock Source | only one subtype-0x0A descriptor (@35); MS: "The driver supports one single clock source only" |
| Every terminal references clock 1 | bCSourceID at offsets 50, 68, 89, 116, 143, 181 all = 1; MS: "Each Terminal Entity must have a valid clock connection" |
| Clock Validity Control present | bmControls @40 = 0x07, D3:2 = 01b (ADC-2 5.2.5.1.2) |
| IAD `bInterfaceCount` = 3 | byte @12; vendor itf 3 correctly outside the audio function |
| Device descriptor 0xEF/0x02/0x01 | from the dump; required for an IAD to be honoured |
| One AC + two AS interfaces | MS: "must implement exactly one AudioControl Interface Descriptor ... and one or more AudioStreaming Interface Descriptors" |
| AC interface 1/1/0x20, AS interfaces 1/2/0x20 | bytes @197-199, @206-208, @252-254, @261-263; matches `usbaudio2.inf` compatible IDs |
| AS alt 0 has zero endpoints | nEP @196 and @251 both 0; MS: "must start with alternate setting zero with no endpoint" |
| Each nonzero alt has one iso data endpoint | nEP @205, @260 both 1; MS: "A nonzero alternate setting without any endpoint isn't supported" |
| `bTerminalLink` targets real terminals | 2 @213 → IT 2 @43; 8 @268 → OT 8 @173 |
| `bTerminalLink` identical across alts | only one nonzero alt per interface, so trivially satisfied |
| `bFormatType` consistent | AS_GENERAL @215 = 1 vs FORMAT_TYPE @229 = 1; AS_GENERAL @270 = 1 vs FORMAT_TYPE @284 = 1. MS: "must be identical" |
| `bmFormats` exactly one bit | 0x00000001 at @216-219 and @271-274. MS: "For Type I formats, exactly one bit must be set to one ... Otherwise, the driver ignores the format" |
| `bSubslotSize`/`bBitResolution` = 4 / 24 | @230-231, @285-286. MS table: "Type I PCM format: 1 <= bSubslotSize <= 4, 8 <= bBitResolution <= 32" |
| `wMaxPacketSize` 128 @ bInterval 1 | `TUD_AUDIO_EP_SIZE(true, 96000, 4, 2)` = 104 <= 128 |
| CS_ENDPOINT contents irrelevant | MS: "The fields bmControls, bLockDelayUnits, and wLockDelay are ignored"; also "The MaxPacketsOnly flag in the bmAttributes field isn't supported and is ignored" |
| No feedback endpoint needed | OUT is Synchronous (and known-good is Adaptive); feedback is mandatory only for Asynchronous OUT |
| Mic ITs: 2 channels, bmChannelConfig 0 | TinyUSB's working `MIC_FOUR_CH` does the same (4 channels, NON_PREDEFINED) |
| Selector Unit `bLength` = 10 | 7 + bNrInPins(3) = 10, correct; MS: "The driver supports all entity types defined in ADC-2 3.13" and Selector Control is in the supported-requests table |
| No Processing or Extension Units | MS restricts those to one input pin; we have none |
| No cyclic paths | 2→4→3 and 9/11/13→10/12/14→15→8 are both acyclic |
| All other `bLength` values | IT 17, OT 12, AC header 9, AS_GENERAL 16, FORMAT_TYPE 6, CS_EP 8, SU 10 — all match ADC-2 section 4 fixed sizes |
| AC header `bmControls` = 0x01 | Latency Control read-only; known-good passes a bit *position* (0) where a value belongs, so ours is if anything more correct |
| `bCategory` = 0x04 | identical to the known-good `AUDIO20_FUNC_HEADSET` |

One further low-confidence note, kept separate because I could not verify it:
searches surfaced a wdmaudiodev thread claiming "some AC Units may not be
supported by Microsoft's usbaudio2.sys", but the page returned **HTTP 403** and I
could not read it, and the Microsoft doc states the opposite ("supports all
entity types defined in ADC-2 3.13", with Selector Unit in the request table).
**HYPOTHESIS, unverified, low:** if everything else fails, collapsing the record
topology to one mic (IT 9 → FU 10 → OT 8, deleting SU 15 and two IT/FU pairs)
reproduces the known-good shape almost exactly and frees 64 bytes.

---

## 5. Recommended test order

Ranked by likelihood, the order is #1, #2, #3/#4. Ranked by **cost**, three of
the four are single-byte edits that do not move any other byte. Suggested
sequence:

**Round 3a — 4 bytes changed, zero length impact, no lengths to recompute:**

| offset | from | to | defect |
|---|---|---|---|
| 39 | `01` | `03` | #3 clock → internal programmable |
| 235 | `0d` | `09` | #4 OUT → Adaptive |
| 276 | `04` | `00` | #2 record bmChannelConfig → 0x00000000 |
| 290 | `0d` | `05` | #4 IN → Asynchronous |

If Windows still reports Event ID 34 after 3a, the remaining non-compliance is
almost certainly the Feature Unit lengths.

**Round 3b — defect #1**, the full `bLength` 10 → 18 fix on all four Feature
Units plus the two `wTotalLength` updates (table in section 3, defect #1), or the
-22-byte shrinking variant if flash layout is fixed.

Keep 3a and 3b separate: 3a is free and reversible, 3b relocates every byte after
offset 80 and is the one that can introduce new arithmetic mistakes.
