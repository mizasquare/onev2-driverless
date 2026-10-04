# Apogee ONE (2nd gen) — driverless firmware patch

Patches the firmware of the 2013 **Apogee ONE for iPad & Mac** (USB `0c60:0017`, product string
`ONEv2`) so that it

- records and plays on **Windows 11, macOS and iPad (USB-C)** with the drivers those systems
  already ship — no Apogee driver, no Apogee app;
- lets the **knob on the device** switch the mic input between Internal, External and
  External + 48 V, which previously only Apogee's software could do.

Apogee's own iPad Maestro app keeps working after the patch.

| Platform                                     | Record   | Play     | Knob input switching |
| -------------------------------------------- | -------- | -------- | -------------------- |
| Windows 11, inbox `usbaudio2.sys`            | verified | verified | verified             |
| macOS (M1 MacBook, Tahoe)                    | verified | verified | verified             |
| iPad USB-C (iPad Pro M2, iPadOS 27.2 beta)   | verified | verified | verified             |

Verified on real hardware with the **patched firmware**. Patching itself has only been done from
Windows.

## How to patch

You do not need to know Python or open a terminal.

1. **Windows:** follow [docs/WINDOWS-SETUP.md](docs/WINDOWS-SETUP.md) once (a short Zadig step so
   the tools can reach the device), then double-click **`PATCH-ME-WINDOWS.bat`**.
   **macOS:** double-click **`PATCH-ME-MAC.command`** — no setup needed. *(Untested: nobody has
   patched from a Mac yet. If you try, please open an issue either way.)*
   **iPad:** cannot patch itself — patch from a PC or Mac, then use it on the iPad.
2. In the menu, work down the list: **1** check → **2** back up your firmware (do not skip) →
   **3** build → **4** flash → **5** test. Item **6** is the undo button.

The launcher installs what it needs into a `.venv` inside this folder; your system Python is left
alone. No firmware is included here — item 2 reads yours out of your own device.

## Before you flash

- **Read [SAFETY.md](SAFETY.md).** It is short.
- **Reversible:** the device has two firmware slots and only the unused one is ever written.
  Menu item 6 switches back to the old one.
- **Not reversible:** if a patched image passes its checksum but fails to boot, there is no USB
  rescue — only JTAG (opening the case and soldering). Tested on two units, one factory firmware
  version (1.05); keep a spare if you have one.
- **48 V phantom power:** after patching, a long press on the knob can switch phantom power on.
  Unplug anything on the XLR that should not see it (ribbon mics, unbalanced sources).
- Patching voids any remaining warranty.

## What to expect

This project was **vibecoded**: essentially all code and reverse engineering came from Claude
(Anthropic), and the human author owns the hardware, set the goals and ran every physical test —
but has no firmware-engineering credentials, and nobody with them has reviewed it. The results
above are measured; the claim that the overwritten code is truly unused is reasoned, not proven.
It has run for days, not months. [docs/EVIDENCE-AND-LIMITS.md](docs/EVIDENCE-AND-LIMITS.md) says
exactly which is which.

Everything comes with **no warranty** (MIT, see [LICENSE](LICENSE)). You flash at your own risk.

## Going deeper

- [What the patch changes](docs/WHAT-THE-PATCH-CHANGES.md) — descriptor fields and the 82-byte code patch
- [Evidence and limits](docs/EVIDENCE-AND-LIMITS.md) — measured vs argued vs unknown; where firmware comes from
- [Windows setup](docs/WINDOWS-SETUP.md) — Zadig / WinUSB in detail
- [Tinkering](docs/TINKERING.md) — control protocol, command line, repo layout, full doc index

*Apogee® and Apogee ONE® are trademarks of Apogee Electronics Corporation. This project is not
affiliated with, authorised by, endorsed by or sponsored by it; the names identify the hardware
only. No Apogee firmware, software or documentation is redistributed here. This is independent
reverse engineering for interoperability, on hardware the author owns.*

Authors: **Sukwoon Song** (hardware, decisions, testing) and **Claude** (reverse engineering and
code).
