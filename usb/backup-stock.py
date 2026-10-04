#!/usr/bin/env python3
"""Read the firmware out of your own ONE and write the two image files the patcher needs.

This replaces hunting down Apogee's Maestro package. The device can read its own flash over the
same vendor channel the flasher uses, and a stock image file turns out to be nothing but

    a 4-byte reset vector  +  zeros up to the bank  +  the bank's contents

so the files can be rebuilt exactly. That the rebuild is exact was checked against Apogee's own
ONEv2_USB_Audio_Image0.bin and Image1.bin: both come back byte-identical.

Read-only as far as the device is concerned. It writes two files on your computer and nothing to
the ONE.

    python backup-stock.py                  # writes ../firmware/
    python backup-stock.py --out somewhere  # writes somewhere else
    python backup-stock.py --overwrite      # replace files already in firmware/
    python backup-stock.py --accept-non-factory   # save a bank that is not factory
"""
import argparse, datetime, hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# line_buffering so prompts reach the user the moment they are printed, even when
# something upstream is capturing this script's output into a pipe.
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
import onev2_flash as F

BANKS = {0: (0x4000, 0x180B8), 1: (0x24000, 0x380B8)}
SIZES = {0: 98488, 1: 229560}
CFG_SIG = bytes.fromhex("09025401040100c005")
STOCK_BCD = 0x0105


def reset_vector(to_file_offset):
    """The word at file offset 0: bral from 0 to the bank's first instruction. Computed, not
    copied -- 111 | disp21[20:17] | 0100 | disp21[16] | cond4=al | disp21[15:0], PC + (disp << 1)."""
    disp = to_file_offset >> 1
    w = ((0b111 << 29) | (((disp >> 17) & 0xF) << 25) | (0b0100 << 21)
         | (((disp >> 16) & 1) << 20) | (0xF << 16) | (disp & 0xFFFF))
    return struct.pack(">I", w)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "firmware"))
    ap.add_argument("--overwrite", "--force", dest="overwrite", action="store_true",
                    help="replace files that already exist in the output directory")
    ap.add_argument("--accept-non-factory", action="store_true",
                    help="save a bank even though it does not hold factory firmware; what it writes is NOT a factory image, whatever the filename says")
    ap.add_argument("--iface", type=int, default=3)
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    one = F.open_one(args.iface)
    try:
        bcd = one.dev.bcdDevice
        active = one.get_active_image()
        main_at = one.get_address_of_main()
        print("device: bcdDevice %#06x, running bank %d, main at %#010x" % (bcd, active, main_at))

        if bcd != STOCK_BCD:
            print("  note: the bank it is running is not factory firmware. Both banks are read"
                  " and judged on their own below.")

        files = {}
        for bank, (start, end) in BANKS.items():
            print("reading bank %d, flash %#07x..%#07x (%d bytes) ..." % (bank, start, end,
                                                                          end - start))
            body = one.read_flash(F.FLASH_BASE | start, end - start)
            blob = reset_vector(start) + b"\x00" * (start - 4) + body
            assert len(blob) == SIZES[bank], \
                "bank %d rebuilt to %d bytes, expected %d" % (bank, len(blob), SIZES[bank])
            files[bank] = blob
    finally:
        one.close()

    # Each bank is judged on its own. The two banks are allowed to differ -- that is what A/B
    # banks are FOR, and anyone who has already patched once has two different banks.
    print("\nchecking what came back")
    verdict = {}
    for bank, blob in files.items():
        checks, ok = [], True

        def check(name, good):
            nonlocal ok
            ok &= bool(good)
            checks.append("    %-52s %s" % (name, "ok" if good else "FAILED"))

        check("%d bytes" % SIZES[bank], len(blob) == SIZES[bank])
        check("two config descriptors, 340 bytes each", blob.count(CFG_SIG) == 2)
        # the device descriptor carries bcdDevice right after idVendor/idProduct
        j = blob.find(bytes.fromhex("600c1700"))
        check("device descriptor present", j > 0)
        ver = struct.unpack("<H", blob[j + 4:j + 6])[0] if j > 0 else None
        check("bcdDevice is %#06x, the factory version" % STOCK_BCD, ver == STOCK_BCD)
        verdict[bank] = (ok, ver)
        print("  bank %d: %s" % (bank, "FACTORY FIRMWARE" if ok else
                                 ("bcdDevice %#06x, not factory" % ver if ver else "unreadable")))
        print("\n".join(checks))

    good = [b for b in sorted(files) if verdict[b][0]]

    # Only meaningful when both banks claim to be the same firmware: the bodies must then be
    # identical apart from the +0x20000 relocation of every absolute code pointer.
    if len(good) == 2:
        b0 = files[0][BANKS[0][0]:BANKS[0][1]]
        b1 = files[1][BANKS[1][0]:BANKS[1][1]]
        words = sorted({i & ~3 for i in range(min(len(b0), len(b1))) if b0[i] != b1[i]})
        bad = sum(1 for w in words
                  if struct.unpack(">I", b1[w:w + 4])[0] - struct.unpack(">I", b0[w:w + 4])[0]
                  != 0x20000
                  or not 0x80004000 <= struct.unpack(">I", b0[w:w + 4])[0] <= 0x800180B8)
        okr = bool(words) and bad == 0
        print("\n  both banks: differ only by the +0x20000 relocation"
              " (%d words, %d odd)   %s" % (len(words), bad, "ok" if okr else "FAILED"))
        if not okr:
            print("""
  Both banks say they are factory firmware but they are not the same image.
  That should not happen. Nothing written -- re-seat the cable and try again,
  and say so before flashing anything if it repeats.""")
            return 1

    if not good:
        vs = sorted({v for _, v in verdict.values() if v})
        print("""
Neither bank holds firmware version %s.

What that means depends on which you are:

  * You have patched this device before. The backup you took beforehand is
    still your originals -- this cannot recreate them.

  * You have never patched it, and it simply left the factory on a different
    version. These patches were written and tested against 1.05 and only that,
    so they will refuse your images anyway. Apogee's Maestro package carries a
    firmware updater; bring the ONE up to 1.05 with it, then run this again.
    If yours is NEWER than 1.05, please open an issue -- as far as we know 1.05
    was the last.
    https://github.com/mizasquare/onev2-driverless/issues""" % (
            "%x.%02x" % (STOCK_BCD >> 8, STOCK_BCD & 0xFF)))
        if vs:
            print("\n  This device reports: %s"
                  % ", ".join("%x.%02x" % (v >> 8, v & 0xFF) for v in vs))
        if not args.accept_non_factory:
            print("Nothing written. --accept-non-factory saves what is on the banks anyway,\n"
                  "but what it writes will NOT be factory images, whatever the filenames say.")
            return 2
        good = sorted(files)
        print("--accept-non-factory given: writing what is on the banks regardless.\n")
    elif len(good) == 1:
        other = 1 - good[0]
        print("""
Only bank %d holds factory firmware; bank %d holds something else, so only one
of the two files can be saved from this device.

The patcher needs both. The way out is to put the factory image back into bank
%d as well and run this again -- but that needs the file this cannot give you.
If you have no backup at all, get the images from Apogee's Maestro package once;
after that this tool covers you.""" % (good[0], other, other))
        if not args.accept_non_factory:
            print("\nWriting only bank %d's file. --accept-non-factory would write both," % good[0])
        else:
            good = sorted(files)

    print("\nwriting")
    info = ["Backup taken %s" % datetime.datetime.now().isoformat(timespec="seconds"),
            "bcdDevice %#06x, running bank %d, main at %#010x" % (bcd, active, main_at), ""]
    for bank in good:
        blob = files[bank]
        p = os.path.join(out, "ONEv2_USB_Audio_Image%d.bin" % bank)
        if os.path.exists(p) and not args.overwrite:
            print("  %s already exists, left alone (use --overwrite to replace it)" % p)
            continue
        open(p, "wb").write(blob)
        h = hashlib.sha256(blob).hexdigest()
        print("  %s  %d bytes" % (p, len(blob)))
        print("      sha256 %s" % h)
        info.append("ONEv2_USB_Audio_Image%d.bin  %d bytes  sha256 %s" % (bank, len(blob), h))
    open(os.path.join(out, "BACKUP-INFO.txt"), "w", encoding="utf-8").write("\n".join(info) + "\n")

    print("\nKeep %s. %s your way back to exactly this firmware, and the patcher"
          % ("these two files" if len(good) == 2 else "this file",
             "They are" if len(good) == 2 else "It is part of"))
    print("builds every patched image from %s." % ("them" if len(good) == 2 else "it"))
    return 0 if len(good) == 2 else 3


if __name__ == "__main__":
    sys.exit(main())
