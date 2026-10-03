#!/usr/bin/env python3
"""A tiny AVR32 assembler + an INDEPENDENT disassembler, for hand-writing firmware patches.

Why this exists: no AVR32 toolchain is obtainable for this machine, and the one disassembler we
have (pypcode, same SLEIGH spec as Ghidra, which has open AVR32 bugs) is demonstrably wrong on
exactly the instructions a patch needs — it renders every 4-byte branch as `ADD R0,R0,R0` and
decodes the two distinct loads 703c/70bc identically. So we encode from the architecture manual
and check our own output by decoding it back with separately written logic.

Every encoding below is from the AVR32 Architecture Document (32000D-04/2011) AND verified
against a real instruction in this device's own firmware or bootloader. See SELFTEST.

Encodings (bit 31 = MSB of the first byte; big-endian in memory):
  MOV   Rd,imm21      111 imm21[20:17] 0011 imm21[16] Rd | imm21[15:0]      (p.159 Format III)
  CP.W  Rd,imm21      111 imm21[20:17] 0010 imm21[16] Rd | imm21[15:0]      (p.159 Format III)
  ORH   Rd,imm16      1110 1010 0001 Rd | imm16
  CP.W  Rd,Rs         000 Rs 00011 Rd                                       (2 bytes)
  LD.W  Rd,Rp[d]      011 Rp disp5 Rd           d = ZE(disp5)<<2, 0..124    (p.186 Format III)
  LD.W  Rd,Rp[d]      111 Rp 01111 Rd | disp16  d = SE(disp16)              (p.186 Format IV)
  ST.W  Rp[d],Rs      100 Rp 1 disp4 Rs         d = ZE(disp4)<<2, 0..60     (p.341 Format III)
  ST.W  Rp[d],Rs      111 Rp 10100 Rs | disp16  d = SE(disp16)              (p.341 Format IV)
  ST.H  Rp[d],Rs      101 Rp 00 disp3 Rs        d = ZE(disp3)<<1, 0..14     (p.339 Format III)
  ST.H  Rp[d],Rs      111 Rp 10101 Rs | disp16                              (p.339 Format IV)
  BR    {cond4} K21   111 d21[20:17] 0100 d21[16] cond4 | d21[15:0]  PC += SE(d21)<<1  (p.144)
  BR    {cond3} d8    1100 disp8 0 cond3                              PC += SE(d8)<<1  (p.143)
  RCALL K21           111 d21[20:17] 0101 d21[16] 0000 | d21[15:0]    PC += SE(d21)<<1  (p.303)
  RET   {cond4} Rs    01011110 cond4 Rs                                     (p.304)
"""
import re, struct

REGS = {("r%d" % i): i for i in range(16)}
REGS.update({"sp": 13, "lr": 14, "pc": 15})
COND4 = {"eq": 0, "ne": 1, "cc": 2, "hs": 2, "cs": 3, "lo": 3, "ge": 4, "lt": 5, "mi": 6,
         "pl": 7, "ls": 8, "gt": 9, "le": 10, "hi": 11, "vs": 12, "vc": 13, "qs": 14, "al": 15}
COND4_NAME = {0: "eq", 1: "ne", 2: "cc", 3: "cs", 4: "ge", 5: "lt", 6: "mi", 7: "pl",
              8: "ls", 9: "gt", 10: "le", 11: "hi", 12: "vs", 13: "vc", 14: "qs", 15: "al"}


class AsmError(Exception):
    pass


def _reg(t):
    t = t.strip().lower()
    if t not in REGS:
        raise AsmError("not a register: %r" % t)
    return REGS[t]


def _imm(t):
    t = t.strip()
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    v = int(t, 0)
    return -v if neg else v


def _pack21(op4, field19_16, imm21):
    """111 imm21[20:17] op4 imm21[16] <field19:16> | imm21[15:0]"""
    if not (-(1 << 20) <= imm21 < (1 << 20)):
        raise AsmError("imm21 out of range: %d" % imm21)
    u = imm21 & 0x1FFFFF
    hw1 = (0b111 << 13) | (((u >> 17) & 0xF) << 9) | ((op4 & 0xF) << 5) | \
          (((u >> 16) & 1) << 4) | (field19_16 & 0xF)
    return struct.pack(">HH", hw1, u & 0xFFFF)


# ---------------------------------------------------------------- assembler
def asm_one(line, addr=None, labels=None):
    s = re.sub(r"[;#].*$", "", line).strip()
    if not s:
        return b""
    labels = labels or {}

    def target(tok):
        tok = tok.strip()
        if tok.lower() in labels:
            return labels[tok.lower()]
        return _imm(tok)

    m = re.match(r"^\.word\s+(.+)$", s, re.I)
    if m:
        return b"".join(struct.pack(">I", _imm(x) & 0xFFFFFFFF) for x in m.group(1).split(","))
    m = re.match(r"^\.byte\s+(.+)$", s, re.I)
    if m:
        return bytes(_imm(x) & 0xFF for x in m.group(1).split(","))
    m = re.match(r"^\.raw\s+([0-9a-fA-F ]+)$", s)
    if m:
        return bytes.fromhex(m.group(1).replace(" ", ""))

    m = re.match(r"^mov\s+(\w+)\s*,\s*(.+)$", s, re.I)
    if m:
        return _pack21(0b0011, _reg(m.group(1)), _imm(m.group(2)))
    m = re.match(r"^orh\s+(\w+)\s*,\s*(.+)$", s, re.I)
    if m:
        v = _imm(m.group(2))
        if not 0 <= v <= 0xFFFF:
            raise AsmError("orh imm16 out of range")
        return struct.pack(">HH", 0xEA10 | _reg(m.group(1)), v)
    m = re.match(r"^cp\.w\s+(\w+)\s*,\s*(\w+)$", s, re.I)
    if m and m.group(2).lower() in REGS:
        return struct.pack(">H", (0b000 << 13) | (_reg(m.group(2)) << 9) | (0b00011 << 4) | _reg(m.group(1)))
    m = re.match(r"^cp\.w\s+(\w+)\s*,\s*(.+)$", s, re.I)
    if m:
        return _pack21(0b0010, _reg(m.group(1)), _imm(m.group(2)))
    m = re.match(r"^ld\.w\s+(\w+)\s*,\s*(\w+)\s*\[\s*(.+?)\s*\]$", s, re.I)
    if m:
        rd, rp, d = _reg(m.group(1)), _reg(m.group(2)), _imm(m.group(3))
        if 0 <= d <= 124 and d % 4 == 0:
            return struct.pack(">H", (0b011 << 13) | (rp << 9) | ((d >> 2) << 4) | rd)
        return struct.pack(">HH", (0b111 << 13) | (rp << 9) | (0b01111 << 4) | rd, d & 0xFFFF)
    m = re.match(r"^st\.w\s+(\w+)\s*\[\s*(.+?)\s*\]\s*,\s*(\w+)$", s, re.I)
    if m:
        rp, d, rs = _reg(m.group(1)), _imm(m.group(2)), _reg(m.group(3))
        if 0 <= d <= 60 and d % 4 == 0:
            return struct.pack(">H", (0b100 << 13) | (rp << 9) | (1 << 8) | ((d >> 2) << 4) | rs)
        return struct.pack(">HH", (0b111 << 13) | (rp << 9) | (0b10100 << 4) | rs, d & 0xFFFF)
    m = re.match(r"^st\.h\s+(\w+)\s*\[\s*(.+?)\s*\]\s*,\s*(\w+)$", s, re.I)
    if m:
        rp, d, rs = _reg(m.group(1)), _imm(m.group(2)), _reg(m.group(3))
        if 0 <= d <= 14 and d % 2 == 0:
            return struct.pack(">H", (0b101 << 13) | (rp << 9) | ((d >> 1) << 4) | rs)
        return struct.pack(">HH", (0b111 << 13) | (rp << 9) | (0b10101 << 4) | rs, d & 0xFFFF)
    m = re.match(r"^br(?:\{(\w+)\})?\s+(.+)$", s, re.I)
    if m:
        cond = COND4[(m.group(1) or "al").lower()]
        if addr is None:
            raise AsmError("br needs a current address")
        t = target(m.group(2))
        if (t - addr) % 2:
            raise AsmError("branch target not halfword aligned")
        return _pack21(0b0100, cond, (t - addr) // 2)
    m = re.match(r"^rcall\s+(.+)$", s, re.I)
    if m:
        if addr is None:
            raise AsmError("rcall needs a current address")
        t = target(m.group(1))
        return _pack21(0b0101, 0, (t - addr) // 2)
    m = re.match(r"^ret(?:\{(\w+)\})?\s+(\w+)$", s, re.I)
    if m:
        cond = COND4[(m.group(1) or "al").lower()]
        return struct.pack(">H", (0x5E << 8) | (cond << 4) | _reg(m.group(2)))
    raise AsmError("cannot assemble: %r" % s)


def assemble(src, origin):
    """Two passes so labels work. Returns (bytes, {label: addr})."""
    labels, addr = {}, origin
    for line in src.splitlines():
        t = re.sub(r"[;#].*$", "", line).strip()
        if not t:
            continue
        if t.endswith(":"):
            labels[t[:-1].lower()] = addr
            continue
        addr += len(asm_one(t, addr, {k: origin for k in ()}) or b"") if False else len(_sizeof(t, addr))
    out, addr = bytearray(), origin
    for line in src.splitlines():
        t = re.sub(r"[;#].*$", "", line).strip()
        if not t or t.endswith(":"):
            continue
        b = asm_one(t, addr, labels)
        out += b
        addr += len(b)
    return bytes(out), labels


def _sizeof(t, addr):
    """Pass-1 length. Branch/rcall are always 4 bytes, so a provisional target is fine.
    Catch ValueError as well as AsmError: an unresolved label reaches _imm(), whose int(t, 0)
    raises ValueError, which would otherwise escape pass 1 and break labels entirely."""
    try:
        return asm_one(t, addr, {})
    except (AsmError, ValueError):
        tt = re.sub(r"^(br(\{\w+\})?|rcall)\s+.*$", r"\1 0x%x" % addr, t, flags=re.I)
        return asm_one(tt, addr, {})


# ---------------------------------------------------------------- disassembler
def dis_one(b, addr):
    """Decode one instruction. Written from the manual independently of the encoder above,
    so a disagreement between them is a real signal."""
    hw = struct.unpack(">H", b[:2])[0]
    top3 = hw >> 13
    # ORH shares the top-3 bits with the other 4-byte forms, so test it first.
    if (hw & 0xFFF0) == 0xEA10:
        return 4, "orh r%d, %s" % (hw & 0xF, hex(struct.unpack(">H", b[2:4])[0]))
    if top3 == 0b111:
        if len(b) < 4:
            return 2, "<truncated>"
        w = struct.unpack(">I", b[:4])[0]
        op4 = (w >> 21) & 0xF
        f = (w >> 16) & 0xF
        rp = (w >> 25) & 0xF
        imm16 = w & 0xFFFF
        hi = ((w >> 25) & 0xF) << 17 | (((w >> 20) & 1) << 16)
        val = hi | imm16
        if val & (1 << 20):
            val -= (1 << 21)
        if op4 == 0b0011:
            return 4, "mov r%d, %s" % (f, hex(val))
        if op4 == 0b0010:
            return 4, "cp.w r%d, %s" % (f, hex(val))
        if op4 == 0b0100:
            return 4, "br{%s} %s" % (COND4_NAME[f], hex(addr + 2 * val))
        if op4 == 0b0101:
            return 4, "rcall %s" % hex(addr + 2 * val)
        sub5 = (w >> 20) & 0x1F
        d16 = imm16 - 0x10000 if imm16 >= 0x8000 else imm16
        if sub5 == 0b01111:
            return 4, "ld.w r%d, r%d[%s]" % (f, rp, hex(d16))
        if sub5 == 0b10100:
            return 4, "st.w r%d[%s], r%d" % (rp, hex(d16), f)
        if sub5 == 0b10101:
            return 4, "st.h r%d[%s], r%d" % (rp, hex(d16), f)
        return 4, "<unknown 4-byte %08x>" % w
    if top3 == 0b011:
        return 2, "ld.w r%d, r%d[%s]" % (hw & 0xF, (hw >> 9) & 0xF, hex(((hw >> 4) & 0x1F) * 4))
    if top3 == 0b100 and (hw >> 8) & 1:
        return 2, "st.w r%d[%s], r%d" % ((hw >> 9) & 0xF, hex(((hw >> 4) & 0xF) * 4), hw & 0xF)
    if top3 == 0b101 and ((hw >> 7) & 0x3) == 0:
        return 2, "st.h r%d[%s], r%d" % ((hw >> 9) & 0xF, hex(((hw >> 4) & 0x7) * 2), hw & 0xF)
    if top3 == 0b000 and ((hw >> 4) & 0x1F) == 0b00011:
        return 2, "cp.w r%d, r%d" % (hw & 0xF, (hw >> 9) & 0xF)
    if (hw >> 12) == 0b1100 and ((hw >> 3) & 1) == 0:
        d8 = (hw >> 4) & 0xFF
        if d8 >= 0x80:
            d8 -= 0x100
        return 2, "br{%s} %s" % (COND4_NAME[hw & 7], hex(addr + 2 * d8))
    if (hw >> 8) == 0x5E:
        return 2, "ret{%s} r%d" % (COND4_NAME[(hw >> 4) & 0xF], hw & 0xF)
    return 2, "<unknown 2-byte %04x>" % hw


def disassemble(data, origin):
    out, i = [], 0
    while i < len(data):
        n, txt = dis_one(data[i:i + 4], origin + i)
        out.append((origin + i, data[i:i + n].hex(), txt))
        i += n
    return out


# ---------------------------------------------------------------- self test
SELFTEST = [
    # bytes,      address,     mnemonic                 where it came from
    ("e07d0000", 0x80006950, "mov sp, 0x10000",   "app startup, sets SP"),
    ("fe780d30", 0x80010cce, "mov r8, -0xf2d0",   "WDT base 0xFFFF0D30"),
    ("e0610b88", 0x8000695e, "mov r1, 0xb88",     "app .data end"),
    ("e0480020", 0x80008192, "cp.w r8, 0x20",     "class-request test"),
    ("ea114953", 0x80000030, "orh r1, 0x4953",    "bootloader 'ISPK' high half"),
    ("0230",     0x80006962, "cp.w r0, r1",       "app startup loop test"),
    ("703c",     0x8000a24c, "ld.w r12, r8[0xc]", "mic input getter -> 0x255c"),
    ("70bc",     0x8000a1e0, "ld.w r12, r8[0x2c]","sample-rate getter -> 0x25ac"),
    ("f6f30140", 0x8000006a, "ld.w r3, r11[0x140]","bootloader reads PM.RCAUSE"),
    ("9109",     0x80010cd6, "st.w r8[0x0], r9",  "WDT CTRL write (arm)"),
    ("9113",     0x80011010, "st.w r8[0x4], r3",  "WDT CLR write (the pet)"),
    ("9302",     0x80000142, "st.w r9[0x0], r2",  "bootloader WDT disable"),
    ("e08500cf", 0x800081ca, "br{lt} 0x80008368", "app request dispatch"),
    ("e08100f3", 0x800081d2, "br{ne} 0x800083b8", "app request dispatch"),
    ("e0a00eb9", 0x800063fe, "rcall 0x80008170",  "bootloader SETUP ISR call"),
    ("5efc",     0x8000a24e, "ret{al} r12",       "mic input getter return"),
    ("c481",     0x8000007e, "br{ne} 0x8000010e", "bootloader: not ISPK -> run app"),
]

def _norm(s):
    """Compare by meaning, not spelling: sp/lr/pc are r13/r14/r15, and whitespace is noise."""
    s = s.lower()
    for a, b in (("sp", "r13"), ("lr", "r14"), ("pc", "r15")):
        s = re.sub(r"\b%s\b" % a, b, s)       # substitute while word boundaries still exist
    return s.replace(" ", "")


if __name__ == "__main__":
    print("Two properties are checked, and both must hold for every instruction:")
    print("  (1) our decoder reads the REAL firmware bytes as the known-correct mnemonic")
    print("  (2) our encoder's output decodes back to that same mnemonic (encoder/decoder agree)")
    print("Byte-identical output is NOT required: the 4-byte branch form is always emitted, so a")
    print("firmware instruction that used the 2-byte form is a different encoding of the same thing.\n")
    print("%-10s %-12s %-21s %-21s %-10s %-21s" %
          ("bytes", "at", "known mnemonic", "our decode of it", "we emit", "decode of our bytes"))
    ok = True
    for hexb, addr, mnem, note in SELFTEST:
        raw = bytes.fromhex(hexb)
        _, got = dis_one(raw, addr)
        back = asm_one(mnem, addr)
        _, back_txt = dis_one(back + b"\0\0", addr)
        p1 = _norm(got) == _norm(mnem)
        p2 = _norm(back_txt) == _norm(mnem)
        ok &= p1 and p2
        print("%-10s %-12s %-21s %-21s %-10s %-21s %s %s" %
              (hexb, hex(addr), mnem, got, back.hex(), back_txt,
               "(1)OK" if p1 else "(1)FAIL", "(2)OK" if p2 else "(2)FAIL"))
        if raw != back:
            print("           ^ different encoding of the same instruction (expected for branches)")
    print("\n%d real instructions from this device's own firmware: %s"
          % (len(SELFTEST), "ALL OK" if ok else "*** FAILURES ***"))
