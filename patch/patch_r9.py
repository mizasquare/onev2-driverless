#!/usr/bin/env python3
"""ONEv2 patch, round 9 -- the CODE patch: a long press in mic focus cycles the mic source.

Rounds 2..8 are descriptor-only. This is the first round that changes CODE.
Output: *.R9.patched.bin

WHAT IT DOES, AND WHAT IT COSTS
  Stock: a long press (held 105 main-loop passes) toggles output mute and starts the headphone
  indicator blinking, in any focus state 2..6. Documented by Apogee's own knowledge base ("Hold
  down the knob for a few seconds. This mutes and unmutes the output.") and measured here: two
  long presses moved vendor 0x35 00->01 then 01->00, with event bit 0x08 one-for-one.

  After: in the three MIC focus states (3 Internal, 4 External, 5 External+48V) a long press
  advances the mic source Internal -> External -> External+48V -> Internal, one step per hold.
  In the instrument (2) and output (6) focus states the long press still toggles mute, byte for
  byte Apogee's own code. Mute therefore stays reachable from the panel -- short-press to the
  instrument or speaker stop, then hold -- which also keeps an escape if host software leaves the
  output muted.

  The owner chose this (option A) and accepted that the cycle reaches 48V phantom power, which a
  long press can switch on. One step per hold, so Internal -> +48V is two deliberate holds.

WHERE IT LIVES
  hook        4 bytes at 0x8000CBC8, replacing `rcall 0x8000a208` with `bral 0x8000C5D4`
  trampoline 78 bytes at 0x8000C5D4, inside state 7's handler, which is dead code

  State 7 is an indicator-override display: its TICK paints bits 3/2/1/0 of RAM 0x2660 onto LEDs
  0x10/0x0f/0x11/0x22, ENTER and EXIT blank all four and clear the mask, and a PRESS returns to
  state 6. It is the fine-grained sibling of state 8 (Identify, all lamps on). Unreachable,
  established four ways that do NOT depend on a disassembler staying in sync with the stream:
    - the ONLY 32-bit word in the whole 98,488-byte image pointing into 0x8000C5D4..0x8000C65B is
      vtable entry 7 at 0x8000C3A8, which this patch leaves alone;
    - no 4-byte BR/RCALL anywhere in the body resolves into the region (algebraic scan of every
      even address: 0 hits), and no compact 2-byte branch in the neighbouring handlers does either;
    - the constant 7 is never materialised inside the UI module: `mov Rd,0x7` occurs 40 times in
      the body and 0 times in 0x8000c3b0..0x8000cd00, so no store can put 7 into 0x2648;
    - all 36 `mov Rd,0x2648` sites in the image are inside that same module, so nothing outside it
      even addresses the focus variable.
  And this removes a DISPLAY, not a producer: the three status bits state 7 would have shown are
  still computed and still published to RAM 0x1854+4 by their one writer. Nothing host-visible
  changes.
  Worst case if the region were somehow entered: r6 = 7 passes both compares, falls into the mic
  arm, advances the source once, and returns through `bral 0x8000cb6c` into a correctly framed
  function. Wrong, not a crash, recoverable -- and that bound holds even if all four arguments
  above were wrong.

  The 36 bytes the hook orphans at 0x8000CBCC..0x8000CBEF are deliberately LEFT AS THEY ARE, not
  nop-filled. Filling them gains nothing and would destroy the stock mute code if anything ever
  branched into the middle of that block.

WHY NOT THE FREE TAIL
  32,584 bytes sit erased at 0x800180B8..0x80020000, but FLASHING.md records that the updater
  writes a FIXED window (start 0x4000/0x24000, length 0x1C000) while both files are shorter than
  that window, so whether it pads or truncates is unverified. Dead code inside the existing image
  removes that unknown.

BOTH BANKS
  Built only from PC-relative instructions, no absolute address literal, so the same bytes go to
  file offset X and X+0x20000. The two stock bodies differ in exactly 662 four-byte words, every
  one a clean +0x20000 code pointer.

Also carried: rounds 2-8 exactly as in patch_descriptors_r8.py, with bcdDevice -> 1.12.
"""
import os, struct, hashlib

FWDIR = os.path.join(os.path.dirname(__file__), "..", "firmware")
OUTDIR = FWDIR          # patched images land next to the stock ones, in firmware/
CFG_SIG = bytes.fromhex("09025401040100c005")
DEV_SIG = bytes.fromhex("600c17000501")
SLOT = 340

AC_HEADER, IN_TERM, OUT_TERM, MIXER, SELECTOR, FEATURE, CLOCK_SRC = 1, 2, 3, 4, 5, 6, 0x0a


# ------------------------------------------------- split / join a config descriptor
def split(cfg):
    """Config descriptor bytes -> list of descriptor bytearrays."""
    out, p = [], 0
    while p < len(cfg) and cfg[p]:
        out.append(bytearray(cfg[p:p + cfg[p]]))
        p += cfg[p]
    return out


def join(items):
    return b"".join(bytes(i) for i in items)


def is_cs(d, subtype, in_ac):
    return d[1] == 0x24 and d[2] == subtype


def ac_span(items):
    """Indices of the class-specific AudioControl descriptors (AC_HEADER .. last 0x24 before
    the first endpoint)."""
    first = last = None
    for i, d in enumerate(items):
        if d[1] == 0x24 and d[2] == AC_HEADER and first is None:
            first = i
        elif first is not None and d[1] == 0x24:
            last = i
        elif first is not None and d[1] == 0x05:
            break
    return first, last


def renumber(items):
    """Recompute AC header wTotalLength and config wTotalLength from the actual bytes."""
    first, last = ac_span(items)
    acl = sum(len(items[i]) for i in range(first, last + 1))
    struct.pack_into("<H", items[first], 6, acl)
    total = sum(len(d) for d in items)
    struct.pack_into("<H", items[0], 2, total)
    return total, acl


# ------------------------------------------------- the patches
def round2_round3(items, copy_no):
    """IAD count, drop the duplicate clock, then the four round-3 byte fixes."""
    log = []
    iad = next(d for d in items if d[1] == 0x0b)
    assert iad[3] == 4
    iad[3] = 3
    log.append("IAD bInterfaceCount 4 -> 3")

    clocks = [i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == CLOCK_SRC]
    assert len(clocks) == 2, "expected 2 clock sources"
    del items[clocks[1]]
    log.append("removed the duplicate CLOCK_SOURCE (-8)")

    clk = next(d for d in items if d[1] == 0x24 and d[2] == CLOCK_SRC)
    assert clk[4] == 0x01
    clk[4] = 0x03
    log.append("clock bmAttributes 0x01 -> 0x03 (internal fixed -> programmable)")

    in_ac = True
    for d in items:
        if d[1] == 0x04:
            in_ac = (d[5], d[6]) == (0x01, 0x01)
        elif d[1] == 0x05 and (d[3] & 0x03) == 0x01 and ((d[3] >> 2) & 0x03) == 0x03:
            if d[2] & 0x80:
                d[3] = 0x05
                log.append("iso IN ep %#02x Synchronous -> Asynchronous" % d[2])
            else:
                d[3] = 0x09
                log.append("iso OUT ep %#02x Synchronous -> Adaptive" % d[2])
        elif d[1] == 0x24 and not in_ac and d[2] == 1:
            nch, cc, names = d[10], struct.unpack("<I", d[11:15])[0], d[15]
            if nch == 2 and bin(cc).count("1") == 1 and names == 0:
                # ROUND 7: 0x03 = FRONT_LEFT | FRONT_RIGHT, the same layout the playback stream
                # declares. Round 3 put 0 here (legal, "no defined spatial location"); Windows and
                # macOS accept it, the iPad registers no input at all.
                struct.pack_into("<I", d, 11, 0x03)
                log.append("record AS_GENERAL bmChannelConfig %#010x -> 0x00000003" % cc)

    if copy_no == 1:
        items[0][8] = 0x06
        log.append("copy B marker: bMaxPower 0x05 -> 0x06")
    return log


def round4(items):
    """Collapse the three mic feature units into one after the selector, and widen both."""
    log = []
    feats = [i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == FEATURE]
    sel_i = next(i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == SELECTOR)
    assert len(feats) == 4, "expected 4 feature units, found %d" % len(feats)
    sel = items[sel_i]
    npins = sel[4]
    pins = list(sel[5:5 + npins])

    # the mic feature units are exactly the ones the selector draws from
    mic_fu = [i for i in feats if items[i][3] in pins]
    play_fu = [i for i in feats if i not in mic_fu]
    assert len(mic_fu) == 3 and len(play_fu) == 1, \
        "expected 3 selector-fed FUs and 1 playback FU, got %d/%d" % (len(mic_fu), len(play_fu))

    # keep the first mic FU's control bitmap and string index for the merged unit
    proto = items[mic_fu[0]]
    merged_id = proto[3]
    master_ctrl = bytes(proto[5:9])
    ifeature = proto[-1]

    # the selector now takes its inputs straight from the mic input terminals
    new_pins = [items[i][4] for i in mic_fu]          # each mic FU's bSourceID = its terminal
    sel[5:5 + npins] = bytes(new_pins)
    log.append("SELECTOR_UNIT %d pins %s -> %s" % (sel[3], pins, new_pins))

    # ROUND 6: the selector's iSelector names string 21, which this device does not have.
    # Measured on hardware: GET_DESCRIPTOR(STRING, 21) returns a STALL, while 17..20 answer
    # ('iAP Interface', 'Internal/External Mic + Instrument', 'External 48V + Instrument').
    # A descriptor field that names a missing string makes the host ask for it and get stalled --
    # which is exactly what the post-round-5 trace showed
    # (GET_DESCRIPTOR type 3 index 0x15 -> USBD_STATUS_STALL_PID, 48 times). 0 = no string.
    # This is a pre-existing defect in Apogee's own descriptor, not something our patches caused;
    # it only became reachable once the descriptor started parsing.
    if sel[-1]:
        log.append("SELECTOR_UNIT %d iSelector %d -> 0 (string %d does not exist on this device)"
                   % (sel[3], sel[-1], sel[-1]))
        sel[-1] = 0

    # the output terminal the selector fed now reads from the merged feature unit
    ot = next(d for d in items if d[1] == 0x24 and d[2] == OUT_TERM and d[7] == sel[3])
    ot[7] = merged_id
    log.append("OUTPUT_TERMINAL %d bSourceID %d -> %d" % (ot[3], sel[3], merged_id))

    # widen the playback feature unit to a 2-channel cluster (its source is the stereo USB
    # stream, so left and right each get the same control bitmap as the master)
    pf = items[play_fu[0]]
    assert len(pf) == 10
    items[play_fu[0]] = bytearray(bytes([18, 0x24, FEATURE, pf[3], pf[4]]) +
                                  bytes(pf[5:9]) * 3 + bytes([pf[9]]))
    log.append("FEATURE_UNIT %d (playback) bLength 10 -> 18, bmaControls master/L/R all %s"
               % (pf[3], bytes(pf[5:9]).hex()))

    # drop the three mic feature units (high index first so the rest stay valid)
    for i in sorted(mic_fu, reverse=True):
        log.append("removed FEATURE_UNIT %d (-%d)" % (items[i][3], len(items[i])))
        del items[i]

    # Insert the merged 2-channel feature unit directly after the selector, and give it
    # PER-CHANNEL control bitmaps: channel 1 is the mic (vendor 0x34), channel 2 the instrument
    # (vendor 0x3E). The master bitmap is kept as well -- a host that only reads the primary
    # control still finds one, and per the Microsoft doc a host that sees both prefers the
    # single-channel ones. This is what the 10-byte original could not express at all.
    sel_i = next(i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == SELECTOR)
    # ROUND 5: advertise NO controls on the mic feature unit. Measured on hardware (USB ETW,
    # 2026-10-02): the firmware ANSWERS Feature Unit 4 volume GET RANGE (status 0x0) but STALLs
    # Feature Unit 10 volume GET RANGE (USBD_STATUS_STALL_PID 0xC0000004), and Windows gives up
    # there. Apogee's own software drove mic gain through vendor request 0x34, so this control was
    # never implemented in firmware. Declaring it is what makes the host ask for it.
    merged = bytearray(bytes([18, 0x24, FEATURE, merged_id, sel[3]]) +
                       bytes(12) + bytes([ifeature]))
    items.insert(sel_i + 1, merged)
    log.append("added FEATURE_UNIT %d after SELECTOR_UNIT %d: bLength 18, bmaControls "
               "master/ch1/ch2 all ZERO (was %s)"
               % (merged_id, sel[3], master_ctrl.hex()))
    return log


def round7(items):
    """Give the three mic input terminals the same stereo layout as their AS_GENERAL."""
    log = []
    in_ac = True
    for d in items:
        if d[1] == 0x04:
            in_ac = (d[5], d[6]) == (0x01, 0x01)
        elif d[1] == 0x24 and in_ac and d[2] == IN_TERM and len(d) == 17:
            cc = struct.unpack("<I", d[9:13])[0]
            if d[8] == 2 and cc == 0:
                struct.pack_into("<I", d, 9, 0x03)
                log.append("INPUT_TERMINAL %d bmChannelConfig 0x00000000 -> 0x00000003" % d[3])
    assert len(log) == 3, "expected 3 mic input terminals with no channel layout, got %d" % len(log)
    return log


def round8(items):
    """Remove the Selector Unit and the two input terminals it alone fed."""
    log = []
    sel_i = next(i for i, d in enumerate(items) if d[1] == 0x24 and d[2] == SELECTOR)
    sel = items[sel_i]
    pins = list(sel[5:5 + sel[4]])
    keep = pins[0]

    fu = next(d for d in items if d[1] == 0x24 and d[2] == FEATURE and d[4] == sel[3])
    fu[4] = keep
    log.append("FEATURE_UNIT %d bSourceID %d (selector) -> %d (input terminal)"
               % (fu[3], sel[3], keep))

    del items[sel_i]
    log.append("removed SELECTOR_UNIT %d (-%d)" % (sel[3], 8))

    for pin in pins[1:]:
        j = next(i for i, d in enumerate(items)
                 if d[1] == 0x24 and d[2] == IN_TERM and d[3] == pin)
        log.append("removed INPUT_TERMINAL %d (-%d)" % (pin, len(items[j])))
        del items[j]
    return log


# ------------------------------------------------- the code patch
# Nothing of Apogee's firmware is stored in this file. The mute arm is READ OUT OF THE IMAGE the
# user supplies and re-emitted with its three rcalls retargeted for the new address; the only
# constants here are short fingerprints used to confirm we are looking at the right bytes, and the
# instructions of our own mic arm.
#
# Fingerprints. If any of these fails, this is not the firmware this patch was written and tested
# against, and nothing is written.
FP_LONGPRESS_HEAD = bytes.fromhex("1898ef6800083018ec1c0001ef680014301b")   # block +0x04..+0x16
FP_STATE7_HEAD = bytes.fromhex("ebcd4080581cc3a0c073582cc050583c")          # state 7's prologue
FP_GET_SRC = bytes.fromhex("e0682550703c5efc")        # mov r8,0x2550 / ld.w r12,r8[0xc] / ret r12
FP_SET_SRC = bytes.fromhex("ebcd4080201de0682550")    # stm / sub sp,0x4 / mov r8,0x2550
GET_SRC, SET_SRC = 0x8000A248, 0x8000AA30             # the mic-source getter and setter
HOOK_AT, TRAMP_AT, VTAB7_AT, BLOCK_LEN = 0xCBC8, 0xC5D4, 0xC3A8, 0x28
STATE7_ROOM = 0x88                                    # 136 bytes of dead handler
RCALL_OFFSETS = (0x00, 0x16, 0x22)                    # the three rcalls inside the stock block
RJMP_OFFSET = 0x26                                    # its closing 2-byte rjmp
# sha256 of the 78 trampoline bytes this patch produced for the image it was validated on, with
# every one of the five physical long-press phases passing on hardware.
TRAMPOLINE_SHA256 = "10cd680789fbb58eb5dc8595f4784a1081f8b472f173f5004e6d74e95f9861b8"


def _k21(op4, cond, pc, target):
    """4-byte Format II: 111 | disp21[20:17] | op4 | disp21[16] | cond4 | disp21[15:0];
    PC <- PC + (SE(disp21) << 1). AVR32 Architecture Document 32000D, p.143-144."""
    assert (target - pc) % 2 == 0, "odd branch displacement"
    disp = (target - pc) >> 1
    assert -(1 << 20) <= disp < (1 << 20), "branch out of +/-1 MB range"
    d = disp & 0x1FFFFF
    w = ((0b111 << 29) | (((d >> 17) & 0xF) << 25) | (op4 << 21)
         | (((d >> 16) & 1) << 20) | (cond << 16) | (d & 0xFFFF))
    return struct.pack(">I", w)


def _rcall(pc, target):
    return _k21(0b0101, 0x0, pc, target)


def _bral(pc, target):
    return _k21(0b0100, 0xF, pc, target)


def _brcond(pc, target, cond):
    """2-byte compact: 1100 | disp8 | cond; PC <- PC + (SE(disp8) << 1). Verified against real
    bytes in this firmware: c110 = breq +17 halfwords, c0f0 = breq +15, c021 = brne +2."""
    assert (target - pc) % 2 == 0
    disp = (target - pc) >> 1
    assert -128 <= disp <= 127, "compact branch out of range"
    return struct.pack(">H", 0xC000 | ((disp & 0xFF) << 4) | cond)


BREQ, BRNE = 0x0, 0x1


def _decode_k21_target(word, pc):
    d = ((word >> 25) & 0xF) << 17 | ((word >> 20) & 1) << 16 | (word & 0xFFFF)
    if d & (1 << 20):
        d -= 1 << 21
    return pc + 2 * d


def build_trampoline(data, delta):
    """Assemble the 78 bytes: our mic arm, then Apogee's mute arm lifted out of THIS image."""
    blk_file = HOOK_AT + delta
    blk_pc = 0x80000000 + blk_file
    base = 0x80000000 + TRAMP_AT + delta
    stock = bytes(data[blk_file:blk_file + BLOCK_LEN])

    assert stock[0x04:0x16] == FP_LONGPRESS_HEAD, \
        "the long-press block at %#x does not match this firmware's fingerprint" % blk_file
    targets = {o: _decode_k21_target(struct.unpack(">I", stock[o:o + 4])[0], blk_pc + o)
               for o in RCALL_OFFSETS}
    hw = struct.unpack(">H", stock[RJMP_OFFSET:RJMP_OFFSET + 2])[0]
    disp = (hw >> 4) & 0xFF
    if disp & 0x80:
        disp -= 0x100
    rejoin = blk_pc + RJMP_OFFSET + 2 * disp

    mute_at = base + 0x24                       # the mic arm is exactly 0x24 bytes long
    mic = (bytes.fromhex("5826")                                   # cp.w r6, 0x2
           + _brcond(base + 0x02, mute_at, BREQ)                   # instrument focus -> mute
           + bytes.fromhex("5866")                                 # cp.w r6, 0x6
           + _brcond(base + 0x06, mute_at, BREQ)                   # output focus -> mute
           + bytes.fromhex("3018" "ef680014")                      # latch = 1
           + _rcall(base + 0x0E, GET_SRC + delta)                          # r12 = mic source
           + bytes.fromhex("2ffc" "583c")                          # +1 ; cp.w r12,0x3
           + _brcond(base + 0x16, base + 0x1A, BRNE)               # skip the wrap
           + bytes.fromhex("300c")                                 # mov r12,0x0
           + bytes.fromhex("304b")                                 # mov r11,0x4  -> raises 0x29 b4
           + _rcall(base + 0x1C, SET_SRC + delta)                          # set the source
           + _bral(base + 0x20, rejoin))
    assert len(mic) == 0x24, "mic arm is %d bytes, expected 0x24" % len(mic)

    mute = (_rcall(mute_at + 0x00, targets[0x00])
            + stock[0x04:0x16]
            + _rcall(mute_at + 0x16, targets[0x16])
            + stock[0x1A:0x22]
            + _rcall(mute_at + 0x22, targets[0x22])
            + _bral(mute_at + 0x26, rejoin))
    assert len(mute) == BLOCK_LEN + 2, "mute arm is %d bytes" % len(mute)

    tramp = mic + mute
    assert len(tramp) <= STATE7_ROOM, "trampoline does not fit state 7's %d bytes" % STATE7_ROOM
    digest = hashlib.sha256(tramp).hexdigest()
    assert digest == TRAMPOLINE_SHA256, (
        "the assembled trampoline is %s, not the %s that was validated on hardware -- your "
        "firmware differs from the one this patch was written for, so STOP"
        % (digest[:16], TRAMPOLINE_SHA256[:16]))
    return tramp, targets, rejoin


def round9_code(data, delta, log):
    """Install the hook and the trampoline. Every address is checked against the bytes that must
    be there, so a wrong offset cannot write anywhere."""
    hook, tramp, vt = HOOK_AT + delta, TRAMP_AT + delta, VTAB7_AT + delta

    got = struct.unpack(">I", data[vt:vt + 4])[0]
    want = 0x80000000 + TRAMP_AT + delta
    assert got == want, "vtable entry 7 @%#x is %#010x, expected %#010x" % (vt, got, want)
    log.append("vtable entry 7 @%#07x -> %#010x : the trampoline site, left untouched" % (vt, got))

    assert data[tramp:tramp + len(FP_STATE7_HEAD)] == FP_STATE7_HEAD, \
        "state 7's handler @%#x does not start with the expected prologue" % tramp
    for addr, fp, what in ((GET_SRC, FP_GET_SRC, "mic-source getter"),
                           (SET_SRC, FP_SET_SRC, "mic-source setter")):
        off = addr - 0x80000000 + delta
        assert data[off:off + len(fp)] == fp, \
            "the %s at %#010x does not match its fingerprint" % (what, addr + delta)
    log.append("fingerprints ok: state 7 prologue, mic-source getter %#010x, setter %#010x"
               % (GET_SRC + delta, SET_SRC + delta))

    blob, targets, rejoin = build_trampoline(data, delta)
    log.append("mute arm lifted from the image: rcall targets %s, rejoin %#010x"
               % (", ".join("%#010x" % targets[o] for o in RCALL_OFFSETS), rejoin))

    data[tramp:tramp + len(blob)] = blob
    log.append("trampoline @%#07x : %d of the %d dead bytes used, %d spare, sha256 %s"
               % (tramp, len(blob), STATE7_ROOM, STATE7_ROOM - len(blob), TRAMPOLINE_SHA256[:16]))
    data[hook:hook + 4] = _bral(0x80000000 + hook, want)
    log.append("hook @%#07x : the long-press entry now brals to %#010x" % (hook, want))
    log.append("%d orphaned bytes @%#07x left as they are, not nop-filled"
               % (BLOCK_LEN - 4, hook + 4))
    return 4 + len(blob)


# ------------------------------------------------- verification
def ac_entities(items):
    """Only the class-specific descriptors of the AudioControl interface. Scoping matters:
    CS_INTERFACE subtype numbering is context dependent, so an AudioStreaming FORMAT_TYPE
    (subtype 2) would otherwise be mistaken for an AudioControl INPUT_TERMINAL."""
    first, last = ac_span(items)
    return items[first:last + 1]


def channels_of(items, entity_id, depth=0):
    """Trace an entity back to an input terminal to learn its cluster's channel count."""
    assert depth < 16, "topology loop"
    for d in ac_entities(items):
        if d[1] != 0x24:
            continue
        if d[2] == IN_TERM and d[3] == entity_id:
            return d[8]
        if d[2] == FEATURE and d[3] == entity_id:
            return channels_of(items, d[4], depth + 1)
        if d[2] == SELECTOR and d[3] == entity_id:
            chs = {channels_of(items, p, depth + 1) for p in d[5:5 + d[4]]}
            assert len(chs) == 1, "selector %d mixes channel counts %s" % (entity_id, chs)
            return chs.pop()
    raise AssertionError("entity %d not found" % entity_id)


def verify(items, label):
    checks = []
    ids = {}
    acd = ac_entities(items)
    for d in acd:
        if d[1] == 0x24 and d[2] in (IN_TERM, OUT_TERM, MIXER, SELECTOR, FEATURE, CLOCK_SRC):
            checks.append(("entity id %d is unique" % d[3], d[3] not in ids))
            ids[d[3]] = d

    # every feature unit's bLength must match its source cluster
    for d in acd:
        if d[1] == 0x24 and d[2] == FEATURE:
            nch = channels_of(items, d[4])
            want = 6 + (nch + 1) * 4
            checks.append(("FEATURE_UNIT %d bLength %d == 6+(%d+1)*4 = %d"
                           % (d[3], len(d), nch, want), len(d) == want))
    # every bSourceID / selector pin must resolve
    for d in acd:
        if d[1] != 0x24:
            continue
        if d[2] in (OUT_TERM,):
            checks.append(("OUTPUT_TERMINAL %d source %d resolves" % (d[3], d[7]), d[7] in ids))
        if d[2] == FEATURE:
            checks.append(("FEATURE_UNIT %d source %d resolves" % (d[3], d[4]), d[4] in ids))
        if d[2] == SELECTOR:
            for p in d[5:5 + d[4]]:
                checks.append(("SELECTOR_UNIT %d pin %d resolves" % (d[3], p), p in ids))
    # Every string index the descriptor names must actually exist on this device. Measured set:
    # 1,2,3 (manufacturer/product/serial) and 17..20; 4..16 and 21+ all STALL.
    EXISTING = {0, 1, 2, 3, 17, 18, 19, 20}
    for d in items:
        bt = d[1]
        idxs = []
        if bt == 0x02: idxs = [(d[6], "config iConfiguration")]
        elif bt == 0x0b: idxs = [(d[7], "IAD iFunction")]
        elif bt == 0x04: idxs = [(d[8], "interface %d iInterface" % d[2])]
        elif bt == 0x24 and d[2] in (IN_TERM, OUT_TERM, FEATURE, SELECTOR, CLOCK_SRC) and d in acd:
            idxs = [(d[-1], "subtype %#x id %d trailing iString" % (d[2], d[3]))]
            if d[2] == IN_TERM and len(d) == 17:
                idxs.append((d[13], "INPUT_TERMINAL %d iChannelNames" % d[3]))
        for v, what in idxs:
            checks.append(("string index %d (%s) exists" % (v, what), v in EXISTING))

    # ROUND 7: the capture cluster must declare the same stereo layout as playback, and the
    # selector's pins must still all agree -- a Selector Unit may only switch identical clusters.
    as_cc, in_as = [], False
    for d in items:
        if d[1] == 0x04:
            in_as = (d[5], d[6]) == (0x01, 0x02)
        elif d[1] == 0x24 and in_as and d[2] == 1:
            as_cc.append((d[3], d[10], struct.unpack("<I", d[11:15])[0]))
    checks.append(("both AS_GENERAL declare bmChannelConfig 0x3 (%s)" % as_cc,
                   all(cc == 0x03 for _, _, cc in as_cc) and len(as_cc) == 2))
    mic_cc = [(d[3], struct.unpack("<I", d[9:13])[0]) for d in acd
              if d[1] == 0x24 and d[2] == IN_TERM and len(d) == 17 and d[8] == 2
              and (d[4] | (d[5] << 8)) == 0x0201]
    checks.append(("every microphone INPUT_TERMINAL is stereo L/R (%s)" % mic_cc,
                   len(mic_cc) >= 1 and all(cc == 0x03 for _, cc in mic_cc)))
    sels = [d for d in acd if d[1] == 0x24 and d[2] == SELECTOR]
    if sels:
        pin_cc = set()
        for p in sels[0][5:5 + sels[0][4]]:
            t = next(x for x in acd if x[1] == 0x24 and x[2] == IN_TERM and x[3] == p)
            pin_cc.add((t[8], struct.unpack("<I", t[9:13])[0]))
        checks.append(("all selector pins carry one identical cluster (%s)" % pin_cc,
                       len(pin_cc) == 1))
    else:
        # ROUND 8 removed it on purpose; make sure nothing still points at a selector.
        checks.append(("no SELECTOR_UNIT remains", True))
        ot8 = next(d for d in acd if d[1] == 0x24 and d[2] == OUT_TERM
                   and (d[4] | (d[5] << 8)) == 0x0101)
        chain = next(d for d in acd if d[1] == 0x24 and d[2] == FEATURE and d[3] == ot8[7])
        term = next((d for d in acd if d[1] == 0x24 and d[2] == IN_TERM and d[3] == chain[4]), None)
        checks.append(("capture chain is IT -> FU %d -> OT %d" % (chain[3], ot8[3]),
                       term is not None and (term[4] | (term[5] << 8)) == 0x0201))

    clocks = [d for d in acd if d[1] == 0x24 and d[2] == CLOCK_SRC]
    checks.append(("exactly one clock source", len(clocks) == 1))
    checks.append(("clock bmAttributes == 0x03", clocks[0][4] == 0x03))
    for d in acd:
        if d[1] == 0x24 and d[2] == IN_TERM and len(d) == 17:
            checks.append(("INPUT_TERMINAL %d references clock %d" % (d[3], clocks[0][3]),
                           d[7] == clocks[0][3]))
    iad = next(d for d in items if d[1] == 0x0b)
    checks.append(("IAD bInterfaceCount == 3", iad[3] == 3))
    isos = [d for d in items if d[1] == 0x05 and (d[3] & 0x03) == 0x01]
    checks.append(("no Synchronous iso endpoint", all(((d[3] >> 2) & 3) != 3 for d in isos)))
    first, last = ac_span(items)
    acl = sum(len(items[i]) for i in range(first, last + 1))
    checks.append(("AC wTotalLength == %d" % acl,
                   struct.unpack("<H", items[first][6:8])[0] == acl))
    total = sum(len(d) for d in items)
    checks.append(("config wTotalLength == %d" % total,
                   struct.unpack("<H", items[0][2:4])[0] == total))
    checks.append(("fits the %d-byte slot (%d)" % (SLOT, total), total <= SLOT))

    ok = all(c[1] for c in checks)
    print("    verify %s:" % label)
    bad = [n for n, g in checks if not g]
    for n, g in checks:
        if not g:
            print("       FAIL %s" % n)
    print("       %d checks, %d failed" % (len(checks), len(bad)))
    return ok


# ------------------------------------------------- main
for name in ("ONEv2_USB_Audio_Image0.bin", "ONEv2_USB_Audio_Image1.bin"):
    src = open(os.path.join(FWDIR, name), "rb").read()
    data = bytearray(src)
    cfgs = [i for i in range(len(data)) if data[i:i + len(CFG_SIG)] == CFG_SIG]
    devs = []
    i = data.find(DEV_SIG)
    while i != -1:
        if data[i - 8] == 0x12 and data[i - 7] == 0x01:
            devs.append(i - 8)
        i = data.find(DEV_SIG, i + 1)
    print("=== %s: configs %s, device descriptor %s ==="
          % (name, [hex(c) for c in cfgs], [hex(d) for d in devs]))
    assert len(cfgs) == 2 and len(devs) == 1

    allok = True
    for n, base in enumerate(cfgs):
        items = split(data[base:base + SLOT])
        log = round2_round3(items, n)
        log += round4(items)
        log += round7(items)
        log += round8(items)
        total, acl = renumber(items)
        print("    copy %d @%#07x -> %d bytes (AC class block %d)" % (n, base, total, acl))
        for line in log:
            print("        %s" % line)
        allok &= verify(items, "copy %d" % n)
        blob = join(items)
        assert len(blob) == total <= SLOT
        data[base:base + SLOT] = blob + b"\x00" * (SLOT - len(blob))   # pad the unused tail

    delta = 0x20000 if name.endswith("Image1.bin") else 0
    clog = []
    nbytes = round9_code(data, delta, clog)
    print("    code patch, %d bytes:" % nbytes)
    for line in clog:
        print("        %s" % line)

    for s in devs:
        assert struct.unpack("<H", data[s + 12:s + 14])[0] == 0x0105
        struct.pack_into("<H", data, s + 12, 0x0112)
        print("    @%#07x bcdDevice 1.05 -> 1.12" % (s + 12))

    dst = os.path.join(OUTDIR, name.replace(".bin", ".R9.patched.bin"))
    open(dst, "wb").write(data)
    diffs = [k for k in range(len(src)) if src[k] != data[k]]
    regions = ([(c, c + SLOT) for c in cfgs] + [(s, s + 18) for s in devs]
               + [(TRAMP_AT + delta, TRAMP_AT + delta + nbytes - 4),
                  (HOOK_AT + delta, HOOK_AT + delta + 4)])
    stray = [d for d in diffs if not any(lo <= d < hi for lo, hi in regions)]
    print("    bytes changed %d, outside descriptor regions %d %s" % (len(diffs), len(stray), stray[:8]))
    print("    wrote %s -> %s\n" % (dst, "ALL OK" if (allok and not stray) else "*** FAIL ***"))
