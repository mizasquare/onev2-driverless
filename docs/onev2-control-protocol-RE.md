# ONEv2 Control Protocol — reverse-engineered reference

Source: `One Firmware Updater.app/Contents/MacOS/One Firmware Updater` (x86_64 slice, symbols intact),
extracted from `One iPad & Mac 2.5C.dmg` (Apogee Maestro 2.5C). Build path in binary:
`/Users/admin/Documents/kevin/Sandbox/ONEv2/Software/Tools/FirmwareUpdateGUI/...`.
Decoded with capstone from `ONEv2USB::USBRequest` and each Set/Get method. All CONFIRMED by disassembly.

## EP0 vendor request wrapper — ONEv2USB::USBRequest(bRequest, dir, valIdx, pData, wLength)

From disassembly of `__ZN8ONEv2USB10USBRequestEhhjPvt`:
- bmRequestType = (dir != 0) ? 0x40 : 0xC0        ; write=0x40 (host->dev), read=0xC0 (dev->host), vendor+device
- bRequest      = arg1
- wValue        = (valIdx >> 16) & 0xFFFF          ; 0 for all simple params
- wIndex        = valIdx & 0xFFFF                  ; channel index for mixer params
- wLength       = arg5
- retries up to 0x63 on write when first transfer fails

SetMicInputType disasm (addr 0x100004f36):
    mov esi, 0x36   ; bRequest
    mov edx, 1      ; dir = write
    xor ecx, ecx    ; valIdx = 0  -> wValue=0, wIndex=0
    mov r9d, 1      ; wLength = 1
    call ONEv2USB::USBRequest
  => control_transfer(0x40, 0x36, 0x0000, 0x0000, [inputType], 1)

## Full request table (bRequest, dir, wLength)

0x14 rd  16  GetMeterData
0x1F rw   1  Meter PeakHold
0x20 rw   1  Meter OverHold
0x26 wr   1  SetIdentify(bool)
0x27 wr   -  ClearMeters
0x28 rd   3  GetFirmwareVersion / GetHardwareUniqueID
0x29 rd   6  GetHardwareChanges         <-- knob/hardware event poll
0x33 rw   1  Output attenuation
0x34 rw   1  Mic preamp gain (signed char, dB)
0x35 rw   1  Output mute (bool)
0x36 rw   1  Mic input TYPE  {0=Int Mic, 1=Ext Mic, 2=Ext Mic 48V}   <-- INPUT SOURCE
0x3E rw   1  Instrument input gain (signed char)
0x3F rw   1  Session token
0x44 rw   1  Grouping (bool)
0x48 rw   1  GetEncoderSelect            <-- which level the knob currently adjusts (SET works too, measured: usb/r9-test.py)
0x4C rw   *  Mixer channel fader (wIndex=channel)
0x4D rw   *  Mixer channel pan
0x4E rw   *  Mixer channel solo
0x4F rw   *  Mixer channel mute
0x52 rw   1  Suspend event / device prefix
0x53 rw   1  Output route/source
0xB6 rw   1  Output reference level (wIndex=channel)

Input-type enum order (0/1/2) inferred from firmware display strings, in this order:
"Internal Mic + Instrument", "External Mic + Instrument", "External 48V + Instrument".
VERIFY by reading 0xC0,0x36 before trusting the mapping.

## The internal mixer and meters, measured on hardware

The request table above came from Apogee's own symbol names. These entries have now been exercised
on a real ONEv2 (firmware R9, no Apogee software installed or running anywhere). Everything in
this section is measured unless marked otherwise.

### What answers, and with how many channels

| bRequest | meaning | channels that answer | values read |
| --- | --- | --- | --- |
| `0x4C` | mixer fader | **4** (wIndex 0–3) | 48, 48, 48, 48 |
| `0x4D` | mixer pan | **2** (wIndex 0–1) | 64, 64 |
| `0x4E` | mixer solo | **3** (wIndex 0–2) | 0, 0, 0 |
| `0x4F` | mixer mute | **3** (wIndex 0–2) | 1, 1, 0 |

wIndex past those ranges stalls. Reproduced with a fresh handle per read, so the counts are real
and not a damaged handle.

**[inferred]** The asymmetry suggests the topology. Pan exists only where a mono source has to be
placed in a stereo bus, so channels 0 and 1 are the two mono inputs, channel 2 is the stereo
software return (already stereo, no pan), and channel 3 has a fader but no mute, solo or pan —
a master. The mute values `1, 1, 0` match a normal DAW workflow: both inputs muted, software
return open.

### Writes are accepted, unvalidated, and inaudible

`0x4C` accepts and reads back **0–255 with no clamping**, including values far outside any
plausible fader range. The firmware stores the byte as given.

Unmuting channel 0 (`0x4F` wIndex 0 = 0) and setting its fader to 70 produced **no audible
monitoring at all**, at either 70 or 48, and the front-panel headphone indicator stayed solid —
so `0x4F` is not the device mute that `0x35` drives. Every value was restored afterwards.

### The meters are live without any host software

`0x14 GetMeterData` returns 16 bytes: **eight 16-bit slots, big-endian**, of which two carry
signal and the rest are zero.

| slot | bytes | what it is | evidence |
| --- | --- | --- | --- |
| A | 0–1 | **mic preamp** | follows `0x36`: Internal mic reads 132–1104 with room noise, switching to External with nothing on the XLR drops it to 26–181 and flattens at ~28 |
| B | 2–3 | **instrument input** | steady 8–12 regardless of `0x36` — the noise floor of an empty jack |

### What this says

The DSP front end **runs with no Apogee software present**: it digitises both inputs and meters
them continuously, with the session token at zero and both mixer channels muted. So the thing that
is inactive is not the DSP but specifically the **monitor-mix path to the headphone output**.

**[hypothesis, untested]** `0x3F` "session token" reads **0** here, and a control app claiming a
session is the obvious candidate for what opens that path. Nothing has been written to `0x3F`.

This matters for anyone thinking of driving the monitor mix from firmware: setting the fader and
mute registers is demonstrably not sufficient.

## Firmware update (DFU) — ApoUSB class

Vendor DFU, NOT standard DFU-class descriptor. Methods:
  EnterDFU, StartDFU, WriteDFUBlock(offset,buf,len), WriteDFUBlocks, ReadDFUStatus, EndDFU,
  SelectFirmwareID, EraseFirmware, SetFlashType, ResetFactorySettingsNVRAM,
  VendorSpecificReset, VendorSpecificRevertNormal, VendorSpecificSetImageType(id),
  VendorSpecificSetRevertId(id), VendorSpecificFinalizeBootPartition.
Device re-enumerates to PID 0x8017 ("Apogee ONE DFU") for flashing.
Dual-bank images: "Active image is %d, writing image: %d"; log "WARNING: running image does not
match - updating to match". Two banks => a bad write to the inactive bank is recoverable.
Firmware images: ONEv2_USB_Audio_Image0.bin (0x4000 header pad + body), Image1.bin (0x24000 pad + body);
bodies differ at offset 0x7e1 (01 vs 03). Plaintext (entropy ~6.9), embeds the exact UAC2 config
descriptor seen on the wire (so descriptor fixes are a data patch). DANGEROUS requests to avoid when
probing: anything in the ApoUSB DFU/VendorSpecific set.

## Minimal read (safe) — libusb/pyusb
  control_transfer(0xC0, 0x36, 0, 0, 1)   # current input type
  control_transfer(0xC0, 0x34, 0, 0, 1)   # current mic gain
  control_transfer(0xC0, 0x48, 0, 0, 1)   # encoder-select state
  control_transfer(0xC0, 0x29, 0, 0, 6)   # hardware-change event block
## Write (one byte)
  control_transfer(0x40, 0x36, 0, 0, bytes([1]))   # -> External Mic
