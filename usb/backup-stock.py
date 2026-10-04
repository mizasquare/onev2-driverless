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
    python backup-stock.py --force          # overwrite existing files, or accept a patched device
"""
import argparse, datetime, hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
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
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing files, and proceed on an already-patched device")
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
            print("\n  !! This device is NOT on factory firmware (bcdDevice %#06x, factory is"
                  " %#06x)." % (bcd, STOCK_BCD))
            print("     A backup taken now captures what is on it NOW, not the factory image.")
            if not args.force:
                print("     Nothing written. Re-run with --force if that is what you want.")
                return 2
            print("     --force given, continuing.\n")

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

    print("\nchecking what came back")
    ok = True

    def check(name, good):
        nonlocal ok
        ok &= bool(good)
        print("  %-56s %s" % (name, "ok" if good else "FAILED"))

    for bank, blob in files.items():
        check("bank %d is %d bytes" % (bank, SIZES[bank]), len(blob) == SIZES[bank])
        check("bank %d holds two config descriptors" % bank, blob.count(CFG_SIG) == 2)
        # the device descriptor carries bcdDevice right after idVendor/idProduct
        j = blob.find(bytes.fromhex("600c1700"))
        check("bank %d device descriptor found" % bank, j > 0)
        if j > 0:
            check("bank %d bcdDevice is %#06x" % (bank, bcd),
                  struct.unpack("<H", blob[j + 4:j + 6])[0] == bcd)

    b0 = files[0][BANKS[0][0]:BANKS[0][1]]
    b1 = files[1][BANKS[1][0]:BANKS[1][1]]
    check("both banks hold the same length of code", len(b0) == len(b1))
    diff = [i for i in range(min(len(b0), len(b1))) if b0[i] != b1[i]]
    words = sorted({i & ~3 for i in diff})
    bad = 0
    for w in words:
        a = struct.unpack(">I", b0[w:w + 4])[0]
        b = struct.unpack(">I", b1[w:w + 4])[0]
        if b - a != 0x20000 or not (0x80004000 <= a <= 0x800180B8):
            bad += 1
    check("the two banks differ only by +0x20000 relocation (%d words, %d odd)"
          % (len(words), bad), words and bad == 0)

    if not ok:
        print("\nSomething above failed, so these files are NOT trustworthy. Nothing written.")
        print("Re-seat the USB cable and try again; if it keeps failing, say so before flashing")
        print("anything.")
        return 1

    print("\nwriting")
    info = ["Backup taken %s" % datetime.datetime.now().isoformat(timespec="seconds"),
            "bcdDevice %#06x, running bank %d, main at %#010x" % (bcd, active, main_at), ""]
    for bank, blob in files.items():
        p = os.path.join(out, "ONEv2_USB_Audio_Image%d.bin" % bank)
        if os.path.exists(p) and not args.force:
            print("  %s already exists, left alone (use --force to overwrite)" % p)
            continue
        open(p, "wb").write(blob)
        h = hashlib.sha256(blob).hexdigest()
        print("  %s  %d bytes" % (p, len(blob)))
        print("      sha256 %s" % h)
        info.append("ONEv2_USB_Audio_Image%d.bin  %d bytes  sha256 %s" % (bank, len(blob), h))
    open(os.path.join(out, "BACKUP-INFO.txt"), "w", encoding="utf-8").write("\n".join(info) + "\n")

    print("\nKeep these two files. They are your way back to exactly this firmware, and the")
    print("patcher builds every patched image from them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
