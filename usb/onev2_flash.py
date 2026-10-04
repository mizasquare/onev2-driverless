#!/usr/bin/env python3
"""
onev2_flash.py — flash / probe an Apogee ONE v2 (0c60:0017) from WINDOWS over raw EP0.

WHY THIS EXISTS
  Apogee's own updater is Intel-Mac-only, which made every patch round a trip to the MacBook.
  This reimplements the updater's flash sequence exactly as recovered by disassembling
  `One Firmware Updater` (x86_64, symbols intact), so descriptor rounds can be iterated on the
  same PC the device is being tested on, with the unit left plugged in.

KEY FINDING (from oneFirmwareUpdateFromFile @0x100006343):
  The ONE does **not** use DFU mode. No PID change, no re-enumeration, no second driver.
  Flashing is done with vendor request 0xA9 against the RUNNING device (PID 0x0017),
  bmRequestType 0x40 (OUT) / 0xC0 (IN), recipient = DEVICE, sub-command in wValue, index in
  wIndex. The ApoUSB class in that binary does also contain a standard USB-DFU implementation
  (DETACH/DNLOAD/GETSTATUS + vendor 0xF0-0xF5), but the ONE update path never touches it —
  that code serves other Apogee products.

  0xA9 sub-commands (wValue), all multi-byte integers BIG-ENDIAN:
    OUT 0  wIndex=0        len 4   SetFlashAddress(addr)        addr = 0x80000000 | file_offset
    OUT 1  wIndex=0..7     len 64  WriteChunk(i, data)          8 chunks = one 512-byte page
    OUT 2  wIndex=0        len 1   CommitFlashPage()            data [0x00]
    IN  3  wIndex=0..7     len 64  ReadChunk(i) -> 64 bytes     read-back verify
    IN  4  wIndex=imgIdx   len 4   GetUserPageCRC(img)          device-computed CRC
    OUT 5  wIndex=imgIdx   len 4   SetUserPageCRC(img, crc)     commit it
    IN  6  wIndex=0        len 4   GetActiveImage() -> byte[3]
    OUT 6  wIndex=imgIdx   len 1   SetActiveImage(img)          data [0x00]
    IN  7  wIndex=0        len 4   GetAddressOfMain() -> addr
  And vendor request 0xA7 OUT, len 1, data [0x00] = soft reset ("resetting ONEv2...").

  Per-page sequence, retried up to 10x on mismatch (updater: "Flash page did not match.
  Retrying flash write." / gives up with "Too many bad flash writes."):
    SetFlashAddress -> 8x WriteChunk -> CommitFlashPage -> 8x ReadChunk -> memcmp(512)

  Bank geometry: bank0 app = file 0x4000..0x20000, bank1 app = file 0x24000..0x40000
  (start + 0x1C000). Only the INACTIVE bank is written. The bootloader at 0x0..0x4000 is
  never written — that is the recovery guarantee.

WINDOWS PREREQUISITE
  Raw EP0 needs WinUSB bound to one interface of the device. Use interface 3 ("iAP Interface",
  MI_03) — it has no driver (problem code 28), so binding WinUSB there leaves usbaudio2 on the
  audio function, i.e. we can flash AND watch Windows accept/reject the descriptors in the same
  session.  See win-flash-setup.md.

SAFETY
  - `probe` and `dump` are READ-ONLY. Run `probe` first: it validates the whole decode by
    reading flash back and comparing against the local .bin, without writing anything.
  - `flash` refuses to run without --yes, never writes outside the target bank's app region,
    and aborts if a page will not verify.
"""
import argparse, hashlib, struct, sys, time, os

try:  # progress lines should appear while they happen, not in one burst at the end
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

if not __debug__:                       # python -O, or PYTHONOPTIMIZE set in the environment
    import sys as _sys
    _sys.exit(
        "\n" + "-" * 78 + "\n"
        "REFUSING to run with assertions disabled (-O, or PYTHONOPTIMIZE set in your\n"
        "environment).\n\n"
        "Much of the checking in this project is written as assert, and -O deletes every\n"
        "one of them. Worse, the output still prints lines like \"fingerprints ok\" --\n"
        "claims that nothing is left to establish. A tool that writes firmware to a device\n"
        "with no USB rescue must not be able to say that falsely.\n\n"
        "Unset PYTHONOPTIMIZE, or run python without -O, and try again.\n"
        + "-" * 78)


VID, PID = 0x0C60, 0x0017
A9 = 0xA9
A7 = 0xA7
PAGE = 0x200
CHUNK = 0x40
CHUNKS = PAGE // CHUNK          # 8
BANK_LEN = 0x1C000
BANK_START = {0: 0x4000, 1: 0x24000}
FLASH_BASE = 0x80000000


# ---------------------------------------------------------------- transport
class One:
    def __init__(self, iface=3, timeout=3000):
        self.iface = iface
        self.timeout = timeout
        self.dev = None
        self._claimed = False
        self.pin = None
        self._open(first=True)

    def _identify(self, dev):
        """A key that survives the device re-enumerating. The USB address does NOT -- it is
        reassigned on every re-enumeration, and reconnect() exists precisely because the device
        re-enumerates under us -- so address is useless here. The serial number is stable and this
        device does publish one; the physical port path is the fallback."""
        try:
            sn = dev.serial_number
            if sn:
                return ("serial", sn)
        except Exception:
            pass
        try:
            return ("port", dev.bus, tuple(dev.port_numbers or ()))
        except Exception:
            return None

    def _candidates(self):
        import libusb_package, usb.core
        backend = libusb_package.get_libusb1_backend()
        return list(usb.core.find(find_all=True, idVendor=VID, idProduct=PID, backend=backend))

    def _open(self, first=False):
        import usb.core, usb.util
        self.usb, self.util = usb.core, usb.util
        found = self._candidates()
        if not found:
            raise IOError("ONEv2 (%04x:%04x) not found by libusb. Is it plugged in?" % (VID, PID))

        if first:
            if len(found) > 1:
                raise SystemExit(
                    "\n%s\n%d Apogee ONEs are connected to this computer.\n\n"
                    "Unplug all but the one you mean to work on, then run this again.\n\n"
                    "This is refused rather than guessed at because the device re-enumerates "
                    "during a\nflash and the handle has to be re-acquired mid-write. With two "
                    "attached, the\nsecond half of an image could land in the other one -- and a "
                    "bank holding half of\neach firmware can still pass its checksum.\n%s"
                    % ("-" * 78, len(found), "-" * 78))
            self.pin = self._identify(found[0])
            dev = found[0]
        else:
            # Re-acquiring after a re-enumeration: take the device we started with, never
            # whatever happens to be enumerated now.
            match = [d for d in found if self.pin is None or self._identify(d) == self.pin]
            if not match:
                raise IOError("the ONE we were working on is not back yet")
            dev = match[0]

        self.dev = dev
        self._claimed = False
        try:
            usb.util.claim_interface(dev, self.iface)
            self._claimed = True
        except Exception as e:
            # Not fatal: device-recipient control transfers may still work.
            if first:
                print("  (note: claim_interface(%d) failed: %s)" % (self.iface, e))
        if first and self.pin:
            print("  working on the ONE identified by %s=%s"
                  % (self.pin[0], self.pin[1] if self.pin[0] == "serial" else self.pin[1:]))

    def reconnect(self, tries=60, delay=0.3):
        """Re-acquire the handle. While usbaudio2 is failing a control request it tears the device
        down and re-enumerates it roughly once a second, which kills our handle mid-operation;
        retrying on a dead handle never recovers, so it has to be re-opened."""
        for _ in range(tries):
            try:
                self.close()
            except Exception:
                pass
            try:
                self._open()
                return True
            except Exception:
                time.sleep(delay)
        return False

    def close(self):
        if self._claimed:
            try: self.util.release_interface(self.dev, self.iface)
            except Exception: pass
        try: self.util.dispose_resources(self.dev)
        except Exception: pass

    def wr(self, bRequest, wValue, wIndex, data):
        n = self.dev.ctrl_transfer(0x40, bRequest, wValue, wIndex, bytes(data), self.timeout)
        if n != len(data):
            raise IOError("short OUT: req %#x val %d idx %d wrote %d/%d"
                          % (bRequest, wValue, wIndex, n, len(data)))

    def rd(self, bRequest, wValue, wIndex, length):
        r = self.dev.ctrl_transfer(0xC0, bRequest, wValue, wIndex, length, self.timeout)
        if len(r) != length:
            raise IOError("short IN: req %#x val %d idx %d got %d/%d"
                          % (bRequest, wValue, wIndex, len(r), length))
        return bytes(r)

    # ----- the 0xA9 sub-commands, named as the updater's log strings name them
    def set_flash_address(self, addr):
        # Hard floor against the one unrecoverable mistake: flash is 256 KB and the address decode
        # ignores bit 18, so 0x80040000 ALIASES ONTO 0x80000000 -- the bootloader's reset vector.
        # A single page written there leaves no app, no DFU and no 0xA9, i.e. JTAG-only recovery.
        # Measured aliasing: read(x) == read(x+0x40000) byte-identical on five address pairs.
        if not (FLASH_BASE <= addr < FLASH_BASE + 0x40000):
            raise SystemExit("REFUSING flash address %#010x: outside %#x..%#x. Addresses at or "
                             "above %#010x alias onto the bootloader."
                             % (addr, FLASH_BASE, FLASH_BASE + 0x40000, FLASH_BASE + 0x40000))
        self.wr(A9, 0, 0, struct.pack(">I", addr))
    def write_chunk(self, i, buf):     self.wr(A9, 1, i, buf)
    def commit_page(self):             self.wr(A9, 2, 0, b"\x00")
    def read_chunk(self, i):           return self.rd(A9, 3, i, CHUNK)
    def get_user_page_crc(self, img):  return struct.unpack(">I", self.rd(A9, 4, img, 4))[0]
    def set_user_page_crc(self, img, crc): self.wr(A9, 5, img, struct.pack(">I", crc))
    def get_active_image(self):        return self.rd(A9, 6, 0, 4)[3]
    def set_active_image(self, img):   self.wr(A9, 6, img, b"\x00")
    def get_address_of_main(self):     return struct.unpack(">I", self.rd(A9, 7, 0, 4))[0]
    def soft_reset(self):              self.wr(A7, 0, 0, b"\x00")

    # ----- descriptors, so every round can verify what is actually live
    def device_descriptor(self):
        return self.rd_std(0x01, 0, 18)

    def config_descriptor(self):
        head = self.rd_std(0x02, 0, 9)
        total = struct.unpack("<H", head[2:4])[0]
        return self.rd_std(0x02, 0, total)

    def rd_std(self, dtype, dindex, length):
        r = self.dev.ctrl_transfer(0x80, 0x06, (dtype << 8) | dindex, 0, length, self.timeout)
        return bytes(r)

    def read_flash(self, addr, nbytes):
        """Read nbytes starting at flash addr (addr must be page aligned). Survives the device
        re-enumerating under us by re-acquiring the handle and redoing the page."""
        out = bytearray()
        for off in range(0, nbytes, PAGE):
            for attempt in range(40):
                try:
                    self.set_flash_address(addr + off)
                    page = b"".join(self.read_chunk(i) for i in range(CHUNKS))
                    break
                except SystemExit:
                    raise
                except Exception as e:
                    if not self.reconnect():
                        raise IOError("lost the device reading %#010x: %s" % (addr + off, e))
            else:
                raise IOError("could not read %#010x after 40 attempts" % (addr + off))
            out += page
        return bytes(out[:nbytes])


# ---------------------------------------------------------------- helpers
ISSUES = "https://github.com/mizasquare/onev2-driverless/issues"
STOCK_BCD = 0x0105
BCD_AT = {0: 0x17600, 1: 0x37600}       # where each bank stores bcdDevice, so one page read tells
                                        # us which firmware is in a bank without scanning it


# Images this project has actually run on hardware. Checked immediately before a write, because
# the flasher is the last thing between a file and flash: everything before it can be skipped by
# pointing it at a file directly.
KNOWN_IMAGES = {
    "e28421fef6df7cef41c39389d115573444a55aac88cecc49f6f17e1082b23e32":
        "factory firmware 1.05, bank 0",
    "804d9d83fb5b3fcb58d08963e36e8e9488e99e3cafbd97299f691c228285f51f":
        "factory firmware 1.05, bank 1",
    "dca0c51268eca7aaf03921004f06f6cf107df2a3f9b86b32677066ca0b63842a":
        "R9 patched, bank 0",
    "c872ea10379824b6df6709a0e0f5848c70c024d32816072494600c83bc242da5":
        "R9 patched, bank 1",
}
CFG_SIG_ANY = bytes.fromhex("0902")
VIDPID = bytes.fromhex("600c1700")


def looks_like_firmware(blob):
    """Does this file even claim to be ONEv2 firmware? Independent of version, so a 1.03 dump
    still passes here -- this only rejects things that are not ONEv2 images at all."""
    for i in range(8, len(blob) - 6):
        if blob[i:i + 4] == VIDPID and blob[i - 8] == 0x12 and blob[i - 7] == 0x01:
            return struct.unpack("<H", blob[i + 4:i + 6])[0]
    return None


def vet_image(blob, name, allow_unknown):
    """Say what we are about to write, and stop if we cannot account for it."""
    h = hashlib.sha256(blob).hexdigest()
    known = KNOWN_IMAGES.get(h)
    if known:
        print("  %s: %s (sha256 %s)" % (os.path.basename(name), known, h[:16]))
        return

    ver = looks_like_firmware(blob)
    if ver is None:
        raise SystemExit(
            "\n%s\nREFUSING to write %s.\n\n"
            "It holds no Apogee ONE device descriptor, so it is not ONEv2 firmware at all --\n"
            "wrong file, or a download that did not finish. sha256 %s\n\n"
            "This one is not overridable. A file like this would be written, pass its CRC\n"
            "because the device computes that itself, and then not boot.\n%s"
            % ("-" * 78, os.path.basename(name), h[:16], "-" * 78))

    if not allow_unknown:
        raise SystemExit(
            "\n%s\nREFUSING to write %s: this project has never run this image.\n\n"
            "  sha256   %s\n"
            "  contents firmware %x.%02x\n\n"
            "It does look like ONEv2 firmware, so this may well be your own build -- but it is\n"
            "not one of the four images that have been tested on hardware, and the device\n"
            "computes the CRC itself, so a broken image still gets blessed and still boots\n"
            "into nothing. There is no USB rescue from that.\n\n"
            "If you built this yourself and know what is in it, pass:\n"
            "    --yes-i-built-this-image\n\n"
            "If you did NOT build it, stop. Rebuild from your own backup with patch_r9.py\n"
            "instead of flashing a file of unknown provenance.\n%s"
            % ("-" * 78, os.path.basename(name), h, ver >> 8, ver & 0xFF, "-" * 78))

    print("  %s: NOT a known image, firmware %x.%02x, sha256 %s"
          % (os.path.basename(name), ver >> 8, ver & 0xFF, h[:16]))
    print("     writing it anyway because --yes-i-built-this-image was given.")


def _ver(v):
    return "firmware %x.%02x" % (v >> 8, v & 0xFF)


R9_BCD = 0x0112


def version_note(bcd):
    """Say plainly what a firmware version means for this toolchain. Printed by probe so that
    somebody on the wrong version learns it at step 1, before a backup has been taken under
    factory filenames and before anything has been built."""
    if bcd == R9_BCD:
        return "  -> this is the R9 patched firmware from this repository."
    if bcd == STOCK_BCD:
        return "  -> factory firmware 1.05, which is what these patches are written for."
    return ("\n  " + "-" * 74 + "\n"
            "  This is firmware %s. These patches are written and tested for FACTORY 1.05\n"
            "  and nothing else -- every flash address in them came out of that one build.\n"
            "\n"
            "  Nothing here will patch this device as it stands, and forcing it past the\n"
            "  checks would write code at addresses that mean something different in your\n"
            "  firmware. There is no USB rescue if that fails to boot.\n"
            "\n"
            "  What to do: Apogee's Maestro package carries a firmware updater. Bring the\n"
            "  ONE up to 1.05 with it, then start again from step 1 here.\n"
            "\n"
            "  If yours is NEWER than 1.05, please open an issue -- as far as we know 1.05\n"
            "  was the last one Apogee shipped.\n"
            "  %s\n"
            "  " + "-" * 74) % (_ver(bcd).replace("firmware ", ""), ISSUES)

def bank_version(one, bank):
    """The bcdDevice a bank reports, read from its one known offset."""
    at = BCD_AT[bank]
    page = one.read_flash(FLASH_BASE | (at & ~0x1FF), PAGE)
    off = at & 0x1FF
    return struct.unpack("<H", page[off:off + 2])[0]


def pick_target(active, main_addr):
    """Reproduce the updater's bank choice, and report disagreement instead of guessing."""
    by_active = 1 if active == 0 else 0
    by_addr = 1 if main_addr < 0x80024000 else 0     # running in bank0 -> write bank1
    if by_active != by_addr:
        print("  WARNING: active-image says write %d but running main address says write %d"
              % (by_active, by_addr))
        print("           (updater prints 'running image does not match' here and trusts the address)")
    return by_addr


SYNC_TYPE = {0: "NoSync", 1: "Async", 2: "Adaptive", 3: "Sync"}

# CS_INTERFACE subtype numbering is CONTEXT DEPENDENT: the same number means different things
# in an AudioControl interface and in an AudioStreaming interface. Getting this wrong makes the
# dump report imaginary terminals, so the two tables are kept separate.
AC_SUBTYPE = {0x01: "AC_HEADER", 0x02: "INPUT_TERMINAL", 0x03: "OUTPUT_TERMINAL",
              0x04: "MIXER_UNIT", 0x05: "SELECTOR_UNIT", 0x06: "FEATURE_UNIT",
              0x07: "EFFECT_UNIT", 0x08: "PROCESSING_UNIT", 0x09: "EXTENSION_UNIT",
              0x0a: "CLOCK_SOURCE", 0x0b: "CLOCK_SELECTOR", 0x0c: "CLOCK_MULTIPLIER",
              0x0d: "SAMPLE_RATE_CONV"}
AS_SUBTYPE = {0x01: "AS_GENERAL", 0x02: "FORMAT_TYPE", 0x03: "FORMAT_SPECIFIC"}


def summarize_config(cfg):
    """One-line-per-descriptor view, enough to confirm which firmware is live."""
    out = []
    p = 0
    in_ac = True                      # until an interface descriptor says otherwise
    while p < len(cfg) and cfg[p]:
        bl, bt = cfg[p], cfg[p + 1]
        tag = {0x02: "CONFIG", 0x04: "INTERFACE", 0x05: "ENDPOINT", 0x0b: "IAD",
               0x24: "CS_INTERFACE", 0x25: "CS_ENDPOINT"}.get(bt, "type%#x" % bt)
        extra = ""
        if bt == 0x02:
            extra = "wTotalLength=%d bNumInterfaces=%d bMaxPower=%d" % (
                struct.unpack("<H", cfg[p+2:p+4])[0], cfg[p+4], cfg[p+8])
        elif bt == 0x0b:
            extra = "first=%d count=%d class=%#x/%#x/%#x" % (cfg[p+2], cfg[p+3], cfg[p+4], cfg[p+5], cfg[p+6])
        elif bt == 0x04:
            in_ac = (cfg[p+5], cfg[p+6]) == (0x01, 0x01)      # AUDIO / AUDIOCONTROL
            extra = "if=%d alt=%d nEP=%d class=%#x/%#x/%#x" % (cfg[p+2], cfg[p+3], cfg[p+4],
                                                               cfg[p+5], cfg[p+6], cfg[p+7])
        elif bt == 0x24:
            st = cfg[p+2]
            name = (AC_SUBTYPE if in_ac else AS_SUBTYPE).get(st, "subtype%#x" % st)
            extra = name
            if in_ac:
                if st == 0x01:
                    extra += " wTotalLength=%d" % struct.unpack("<H", cfg[p+6:p+8])[0]
                elif st == 0x0a:
                    extra += " id=%d bmAttributes=%#02x bmControls=%#02x" % (cfg[p+3], cfg[p+4], cfg[p+5])
                elif st == 0x02:
                    extra += " id=%d clk=%d nCh=%d chCfg=%#010x" % (
                        cfg[p+3], cfg[p+7], cfg[p+8], struct.unpack("<I", cfg[p+9:p+13])[0])
                elif st == 0x03:
                    extra += " id=%d src=%d clk=%d" % (cfg[p+3], cfg[p+7], cfg[p+8])
                elif st == 0x06:
                    extra += " id=%d src=%d nControlBitmaps=%d" % (cfg[p+3], cfg[p+4], (bl - 6) // 4)
                elif st == 0x05:
                    extra += " id=%d nrInPins=%d pins=%s" % (
                        cfg[p+3], cfg[p+4], list(cfg[p+5:p+5+cfg[p+4]]))
            else:
                if st == 0x01:
                    extra += " link=%d bmFormats=%#010x nCh=%d chCfg=%#010x iChNames=%d" % (
                        cfg[p+3], struct.unpack("<I", cfg[p+6:p+10])[0], cfg[p+10],
                        struct.unpack("<I", cfg[p+11:p+15])[0], cfg[p+15])
                elif st == 0x02:
                    extra += " type=%d subslot=%d bits=%d" % (cfg[p+3], cfg[p+4], cfg[p+5])
        elif bt == 0x05:
            attr = cfg[p+3]
            extra = "addr=%#02x attr=%#02x" % (cfg[p+2], attr)
            if (attr & 0x03) == 0x01:
                extra += " ISO/%s" % SYNC_TYPE[(attr >> 2) & 3]
            extra += " wMaxPacket=%d bInterval=%d" % (struct.unpack("<H", cfg[p+4:p+6])[0], cfg[p+6])
        out.append("  %4d  %-13s len=%-3d %s" % (p, tag, bl, extra))
        p += bl
    return "\n".join(out)


# ---------------------------------------------------------------- commands
def cmd_probe(args):
    one = open_one(args.iface)
    try:
        # Standard descriptor reads go through WinUsb_GetDescriptor and can be refused
        # depending on which interface we are attached to; never let that abort the probe.
        try:
            dd = one.device_descriptor()
            bcd = struct.unpack("<H", dd[12:14])[0]
            print("device descriptor: VID %04x PID %04x bcdDevice %x.%02x bcdUSB %04x"
                  % (struct.unpack("<H", dd[8:10])[0], struct.unpack("<H", dd[10:12])[0],
                     bcd >> 8, bcd & 0xFF, struct.unpack("<H", dd[2:4])[0]))
            print(version_note(bcd))
        except Exception as e:
            print("device descriptor: unavailable (%s)" % e)
        try:
            cfg = one.config_descriptor()
            print("config descriptor: %d bytes" % len(cfg))
            print(summarize_config(cfg))
            if args.save_config:
                open(args.save_config, "wb").write(cfg)
                print("  wrote %s" % args.save_config)
        except Exception as e:
            print("config descriptor: unavailable (%s)" % e)

        active = one.get_active_image()
        main_addr = one.get_address_of_main()
        print("\nactive image: %d" % active)
        print("address of main: %#010x  (-> running from bank %d)"
              % (main_addr, 0 if main_addr < 0x80024000 else 1))
        for img in (0, 1):
            try:
                print("user page CRC image %d: %#010x" % (img, one.get_user_page_crc(img)))
            except Exception as e:
                print("user page CRC image %d: FAILED (%s)" % (img, e))

        target = pick_target(active, main_addr)
        print("\n=> a flash now would write image %d (file %#x..%#x)"
              % (target, BANK_START[target], BANK_START[target] + BANK_LEN))

        # The real proof: read flash back and compare with a local image file.
        if args.compare:
            ref = open(args.compare, "rb").read()
            # compare pages from the bank we are RUNNING from — that is what is really in flash
            run_bank = 0 if main_addr < 0x80024000 else 1
            start = BANK_START[run_bank]
            npages = args.pages
            print("\nread-back check: %d pages from %#x (bank %d, the running one) vs %s"
                  % (npages, start, run_bank, os.path.basename(args.compare)))
            ok = bad = 0
            for k in range(npages):
                off = start + k * PAGE
                if off + PAGE > len(ref):
                    break
                got = one.read_flash(FLASH_BASE | off, PAGE)
                if got == ref[off:off + PAGE]:
                    ok += 1
                else:
                    bad += 1
                    if bad <= 3:
                        d = next(i for i in range(PAGE) if got[i] != ref[off + i])
                        print("  MISMATCH at file %#x (+%d): flash %02x vs file %02x"
                              % (off, d, got[d], ref[off + d]))
            print("  pages matching: %d, mismatching: %d" % (ok, bad))
            if bad == 0 and ok > 0:
                print("  => protocol decode CONFIRMED (address mapping, chunk order, endianness).")
            elif ok == 0:
                print("  => no page matched: either the wrong reference file, or the decode is wrong."
                      " Do NOT flash.")
    finally:
        one.close()


def cmd_dump(args):
    one = open_one(args.iface)
    try:
        data = one.read_flash(FLASH_BASE | args.offset, args.length)
        open(args.out, "wb").write(data)
        print("dumped %d bytes from file offset %#x -> %s" % (len(data), args.offset, args.out))
    finally:
        one.close()


def cmd_flash(args):
    img0 = open(args.image0, "rb").read()
    img1 = open(args.image1, "rb").read()
    one = open_one(args.iface)
    try:
        active = one.get_active_image()
        main_addr = one.get_address_of_main()
        target = args.image if args.image is not None else pick_target(active, main_addr)
        print("active image is %d, address of main %#010x -> writing image %d"
              % (active, main_addr, target))
        src = img1 if target == 1 else img0
        name = args.image1 if target == 1 else args.image0
        start = BANK_START[target]
        end = start + BANK_LEN
        print("attempting to write %s to ONEv2 flash image %d (file %#x..%#x, %d bytes of file)"
              % (os.path.basename(name), target, start, min(end, len(src)), len(src)))
        if len(src) > end:
            raise SystemExit("REFUSING: %s is %#x bytes, past this bank's end %#x. A page written "
                             "at or above %#x aliases onto the bootloader."
                             % (os.path.basename(name), len(src), end, FLASH_BASE + 0x40000))
        if len(src) <= start:
            raise SystemExit("REFUSING: %s is only %#x bytes and this bank starts at %#x, so there "
                             "is nothing to write. Did the two image arguments get swapped?"
                             % (os.path.basename(name), len(src), start))
        if not args.yes:
            raise SystemExit("refusing to write without --yes")

        print("what is about to be written:")
        vet_image(src, name, args.yes_i_built_this_image)

        # Do not spend the last bank that still holds factory firmware. Once both banks hold a
        # patched build, "go back" only switches between two patched builds, and the device can no
        # longer produce its own stock images -- the user is down to whatever files they kept.
        if not args.overwrite_factory:
            vt, vo = bank_version(one, target), bank_version(one, 1 - target)
            if vt == STOCK_BCD and vo != STOCK_BCD:
                raise SystemExit(
                    "\n%s\nREFUSING: bank %d is the only one still holding factory firmware "
                    "(%s),\nand bank %d holds %s.\n\n"
                    "Overwriting it leaves the device with no factory firmware of its own. "
                    "\"Go back\"\nwould then switch between two patched builds, and a fresh "
                    "backup could no longer be\ntaken from this device at all -- you would be "
                    "down to the files you have kept.\n\n"
                    "If you want to go back to stock, activate bank %d instead of writing it:\n"
                    "    python onev2_flash.py activate %d\n\n"
                    "If you really do mean to overwrite it, pass --overwrite-factory.\n%s"
                    % ("-" * 78, target, _ver(vt), 1 - target, _ver(vo), target, target, "-" * 78))

        t0 = time.time()
        written = 0
        for off in range(0, len(src), PAGE):
            # `off > end` would let off == end through, writing one page AT the bank end; for
            # bank 1 that is flash 0x80040000, which aliases onto the reset vector.
            if off < start or off + PAGE > end:
                continue
            page = src[off:off + PAGE]
            if len(page) < PAGE:
                page = page + b"\xff" * (PAGE - len(page))
            for attempt in range(40):
                if args.dry_run:
                    break
                try:
                    one.set_flash_address(FLASH_BASE | off)
                    for i in range(CHUNKS):
                        one.write_chunk(i, page[i * CHUNK:(i + 1) * CHUNK])
                    one.commit_page()
                    back = b"".join(one.read_chunk(i) for i in range(CHUNKS))
                except SystemExit:
                    raise                                  # a refused address must never be retried
                except Exception as e:
                    # handle died under us: re-acquire and redo this page. Safe because the page is
                    # only considered done once its read-back matches.
                    if not one.reconnect():
                        raise SystemExit("lost the device at %#08x and could not re-open it: %s"
                                         % (off, e))
                    continue
                if back == page:
                    break
                print("Flash page did not match. Retrying flash write. (offset %#08x, try %d)"
                      % (off, attempt + 1))
            else:
                raise SystemExit("Too many bad flash writes. Firmware update aborted at %#08x." % off)
            written += PAGE
            if (off // PAGE) % 16 == 0:
                pct = 100 * (off - start) // max(1, min(end, len(src)) - start)
                print("  %3d%%  offset %#08x" % (pct, off), end="\r", flush=True)
        print("\n%#08x bytes written to flash image %d successfully. (%.1fs)"
              % (written, target, time.time() - t0))

        if args.dry_run:
            print("dry run: skipping CRC commit / set-active / reset")
            return
        if written == 0:
            # Committing the CRC "blesses" a bank: the bootloader's launcher then runs it instead
            # of failing over to the other one. Doing that after writing nothing would bless
            # whatever happens to be in flash.
            raise SystemExit("REFUSING to commit a CRC: zero pages were written. Nothing has been "
                             "blessed and the active image is unchanged.")
        crc = one.get_user_page_crc(target)
        one.set_user_page_crc(target, crc)
        print("user page CRC: %#010x" % crc)

        # Switching the active image is kept SEPARATE from writing, which the Mac updater does
        # not do. Until it happens the device still boots the other (known-good) bank, so
        # everything up to here is reversible: just don't activate.
        if not args.activate:
            print("\nbank %d is written and verified; the device still boots bank %d."
                  % (target, 1 - target))
            print("To switch over:   python onev2_flash.py activate %d" % target)
            return
        one.set_active_image(target)
        print("active image: %d" % target)
        if args.reset:
            print("resetting ONEv2...")
            try:
                one.soft_reset()
            except Exception as e:
                print("  (reset transfer returned %s — normal if the device detached immediately)" % e)
    finally:
        one.close()


def cmd_activate(args):
    one = open_one(args.iface)
    try:
        was = one.get_active_image()
        print("active image was %d, setting %d" % (was, args.image))
        one.set_active_image(args.image)
        print("active image: %d" % one.get_active_image())
        if args.reset:
            print("resetting ONEv2...")
            try:
                one.soft_reset()
            except Exception as e:
                print("  (reset transfer returned %s — normal if the device detached immediately)" % e)
    finally:
        one.close()


def open_one(iface, tries=60, delay=0.3):
    """Opening can fail simply because the device happens to be mid-re-enumeration right now."""
    last = None
    for _ in range(tries):
        try:
            return One(iface)
        except Exception as e:
            last = e
            time.sleep(delay)
    raise SystemExit("could not open the ONEv2 after %d tries: %s" % (tries, last))


AC_IFACE = 0           # the AudioControl interface number
CUR, RANGE = 0x01, 0x02

def cmd_classreq(args):
    """READ-ONLY: issue the standard UAC2 class GET requests a host driver needs, and report
    which ones the firmware answers vs STALLs. This is what Event 38 ('a control request sent to
    device has failed') is about, and it defines exactly what the firmware code patch must
    implement. GET only -- nothing is set."""
    probes = [
        ("CLOCK_SOURCE 1  sampling frequency  GET CUR",   CUR,   0x01, 1, 4),
        ("CLOCK_SOURCE 1  sampling frequency  GET RANGE", RANGE, 0x01, 1, 64),
        ("CLOCK_SOURCE 1  clock validity      GET CUR",   CUR,   0x02, 1, 1),
        ("SELECTOR_UNIT 15 selector           GET CUR",   CUR,   0x01, 15, 1),
        ("FEATURE_UNIT 10 mute      ch0       GET CUR",   CUR,   0x01, 10, 1),
        ("FEATURE_UNIT 10 volume    ch1       GET CUR",   CUR,   0x02, 10, 2),
        ("FEATURE_UNIT 10 volume    ch1       GET RANGE", RANGE, 0x02, 10, 64),
        ("FEATURE_UNIT 4  mute      ch0       GET CUR",   CUR,   0x01, 4, 1),
        ("FEATURE_UNIT 4  volume    ch1       GET CUR",   CUR,   0x02, 4, 2),
    ]
    one = open_one(args.iface)
    try:
        # Read the result codes carefully, they mean different things:
        #   "Pipe error"            = the device STALLed it. The request reached the firmware.
        #   "Operation not supported" = libusb refused to send it. Says nothing about the device.
        # libusb only routes an interface-recipient request to an interface we have CLAIMED, and
        # we hold interface 3, not the AudioControl interface 0 (usbaudio2 owns that). So aim at
        # the interface we hold: the firmware STALLs class requests regardless of which one.
        print("bmRequestType 0xA1 (IN|class|interface), wIndex = entity<<8 | interface %d" % args.ac_iface)
        print("  'Pipe error' = device STALLed.  'Operation not supported' = libusb would not send it.\n")
        for label, breq, cs, entity, length in probes:
            cn = 1 if "ch1" in label else 0
            wValue = (cs << 8) | cn
            wIndex = (entity << 8) | args.ac_iface
            try:
                r = one.dev.ctrl_transfer(0xA1, breq, wValue, wIndex, length, one.timeout)
                print("  OK      %s  ->  %s" % (label, bytes(r).hex()))
            except Exception as e:
                tag = "STALL " if "Pipe error" in str(e) else "unsent"
                print("  %s  %s  ->  %s" % (tag, label, e))
        # a vendor request for comparison: proves the transport itself is fine
        try:
            print("\n  (control) vendor 0x36 mic input type GET -> %s"
                  % one.rd(0x36, 0, 0, 1).hex())
        except Exception as e:
            print("\n  (control) vendor 0x36 GET failed: %s" % e)
    finally:
        one.close()


def cmd_verify(args):
    """READ-ONLY: read a whole bank back and diff it against a local image file."""
    ref = open(args.file, "rb").read()
    start = BANK_START[args.image]
    one = open_one(args.iface)
    try:
        end = min(start + BANK_LEN, len(ref))
        print("verifying bank %d, file %#x..%#x of %s" % (args.image, start, end, os.path.basename(args.file)))
        bad = []
        for off in range(start, end, PAGE):
            want = ref[off:off + PAGE]
            if len(want) < PAGE:
                want = want + b"\xff" * (PAGE - len(want))
            got = one.read_flash(FLASH_BASE | off, PAGE)
            if got != want:
                bad.append(off)
                if len(bad) <= 5:
                    d = next(i for i in range(PAGE) if got[i] != want[i])
                    print("  MISMATCH file %#08x (+%d): flash %02x vs file %02x"
                          % (off, d, got[d], want[d]))
            if ((off - start) // PAGE) % 32 == 0:
                print("  %#08x" % off, end="\r", flush=True)
        print("\npages mismatching: %d  -> %s" % (len(bad), "BANK MATCHES THE FILE" if not bad else "DO NOT ACTIVATE"))
    finally:
        one.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", type=int, default=3,
                    help="interface to claim for EP0 access (default 3 = the vendor/iAP interface)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="READ-ONLY: ids, descriptors, bank state, read-back check")
    p.add_argument("--compare", help="local .bin to compare flash read-back against")
    p.add_argument("--pages", type=int, default=8, help="pages to read back (default 8 = 4 KB)")
    p.add_argument("--save-config", help="write the live config descriptor to this file")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("dump", help="READ-ONLY: dump flash to a file")
    p.add_argument("offset", type=lambda s: int(s, 0))
    p.add_argument("length", type=lambda s: int(s, 0))
    p.add_argument("out")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("flash", help="write the inactive bank (needs --yes); does NOT switch to it")
    p.add_argument("image0")
    p.add_argument("image1")
    p.add_argument("--image", type=int, choices=(0, 1), help="force target bank instead of auto")
    p.add_argument("--yes", action="store_true", help="actually write")
    p.add_argument("--activate", action="store_true",
                   help="also switch the active image and reset (otherwise do it separately, "
                        "so the write stays reversible)")
    p.add_argument("--yes-i-built-this-image", action="store_true",
                   help="write an image this project has never run. Named so it cannot be typed "
                        "by accident or copied from someone else's command line.")
    p.add_argument("--overwrite-factory", action="store_true",
                   help="allow overwriting the last bank that still holds factory firmware")
    p.add_argument("--dry-run", action="store_true", help="walk the sequence without any OUT transfer")
    p.add_argument("--no-reset", dest="reset", action="store_false", default=True)
    p.set_defaults(func=cmd_flash)

    p = sub.add_parser("activate", help="switch the active image and reset")
    p.add_argument("image", type=int, choices=(0, 1))
    p.add_argument("--no-reset", dest="reset", action="store_false", default=True)
    p.set_defaults(func=cmd_activate)

    p = sub.add_parser("classreq", help="READ-ONLY: which UAC2 class GET requests does the "
                                        "firmware answer? (what Event 38 is about)")
    p.add_argument("--ac-iface", type=int, default=3,
                   help="interface number to put in wIndex. Default 3 (the one we claim, so the "
                        "request actually reaches the device); 0 is the real AudioControl "
                        "interface but libusb will not send there while usbaudio2 owns it.")
    p.set_defaults(func=cmd_classreq)

    p = sub.add_parser("verify", help="READ-ONLY: diff a whole bank against a local image file")
    p.add_argument("image", type=int, choices=(0, 1))
    p.add_argument("file")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
