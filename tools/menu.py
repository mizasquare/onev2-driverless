#!/usr/bin/env python3
"""The menu the launchers show. Nothing here is clever; it runs the scripts in patch/ and usb/
and tries hard to stop you doing them in the wrong order.

Launched by PATCH-ME-WINDOWS.bat / PATCH-ME-MAC.command, which find Python and install the two
packages first. You can also run it directly: python tools/menu.py
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
FW = os.path.join(ROOT, "firmware")
WIN = sys.platform == "win32"
PY = sys.executable

STOCK = ["ONEv2_USB_Audio_Image0.bin", "ONEv2_USB_Audio_Image1.bin"]
PATCHED = ["ONEv2_USB_Audio_Image0.R9.patched.bin", "ONEv2_USB_Audio_Image1.R9.patched.bin"]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def have(names):
    return all(os.path.exists(os.path.join(FW, n)) for n in names)


def _cmd(script, a, unbuffered=False):
    cmd = [PY] + (["-u"] if unbuffered else []) + [os.path.join(ROOT, script)] \
        + [str(x) for x in a]
    print("\n> %s\n" % " ".join(('"%s"' % c if " " in c else c) for c in cmd))
    return cmd


def run(script, *a):
    """Run one of the project's scripts, writing straight to this window.

    Deliberately NOT captured. A captured child writes into a pipe, Python sees that it is not
    a terminal and switches to block buffering, and a script that asks you to physically do
    something then goes silent at exactly the moment it needs you. Only the steps whose output
    has to be parsed are captured, and those pass -u.
    """
    try:
        return subprocess.call(_cmd(script, a), cwd=ROOT)
    except KeyboardInterrupt:
        print("\n(stopped)")
        return 130


def run_capture(script, *a):
    """Run it and keep the output, so numbers can be read out of it instead of being retyped by
    the user. -u so it still appears live on screen."""
    lines = []
    try:
        p = subprocess.Popen(_cmd(script, a, unbuffered=True), cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
                             universal_newlines=True, errors="replace")
        for line in p.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            lines.append(line)
        return p.wait(), "".join(lines)
    except KeyboardInterrupt:
        print("\n(stopped)")
        return 130, "".join(lines)


def running_bank():
    """Which bank the device is running right now, or None if we cannot tell."""
    rc, out = run_capture("usb/onev2_flash.py", "probe")
    if rc != 0:
        return None, out
    m = re.search(r"^active image:\s*(\d)", out, re.M)
    return (int(m.group(1)) if m else None), out


class Closed(Exception):
    """stdin went away -- piped input ran out, or the window was closed."""


def ask(prompt, want=None):
    try:
        a = input(prompt).strip()
    except EOFError:
        print()
        raise Closed()
    except KeyboardInterrupt:
        print()
        return ""
    return a if want is None else a.lower()


def pause():
    try:
        ask("\nPress Enter to go back to the menu. ")
    except Closed:
        pass


# ------------------------------------------------------------------ the steps

def win_state():
    """Ask Windows what it currently thinks the ONE is. Read-only."""
    script = os.path.join(HERE, "win-usb-state.ps1")
    try:
        subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                         "-File", script], cwd=ROOT)
    except Exception as e:
        print("  (could not run the Windows check: %s)" % e)


def step_check():
    print("""
Reading the device. This only reads -- it writes nothing.
""")
    rc = run("usb/onev2_flash.py", "probe")
    if WIN:
        win_state()
    if rc != 0:
        print("""
The device did not answer. If the check above already told you what to do,
do that. Otherwise:

  * Is the ONE plugged into THIS computer? It has to be this one, not the
    iPad and not another Mac.
  * Is the cable a data cable? Plenty of USB-C cables only carry power.""")
        if not WIN:
            print("""  * Is something else holding it? Quit Maestro if it is running.""")
    pause()


def step_backup():
    print("""
This reads the firmware out of your own ONE and saves it as the two files
everything else here is built from.

Do this before anything else. These files are your way back.
""")
    if have(STOCK):
        print("You already have them in firmware/ :")
        for n in STOCK:
            print("    %s   %s bytes" % (n, format(os.path.getsize(os.path.join(FW, n)), ",")))
        if ask("\nRead them off the device again and overwrite? [y/N] ", "") != "y":
            return pause()
        rc = run("usb/backup-stock.py", "--force")
    else:
        rc = run("usb/backup-stock.py")
    if rc == 2:
        print("""
It stopped because this ONE is not on factory firmware any more.

If this is the unit you already patched, that is expected -- and a backup of
what is on it now is still worth having. Choose this menu item again and say
yes when it offers to go ahead anyway, or run:

    %s usb/backup-stock.py --force
""" % os.path.basename(PY))
        if ask("Back up what is on it now anyway? [y/N] ", "") == "y":
            run("usb/backup-stock.py", "--force")
    elif rc == 0:
        print("""
Saved. Copy firmware/ somewhere off this computer as well -- a USB stick, a
cloud folder, anywhere. If you ever lose those two files and Apogee's download
is gone, nobody can give them back to you.""")
    pause()


def step_build():
    if not have(STOCK):
        print("""
There is nothing to build from yet. Do "Back up my firmware" first -- that is
what produces the two input files.""")
        return pause()
    print("""
Building the patched images on this computer. The device is not touched and
does not even need to be plugged in.

The patcher checks your input files against known fingerprints and refuses if
they are not the firmware these patches were written for.
""")
    rc = run("patch/patch_r9.py")
    if rc == 0 and have(PATCHED):
        print("\nBuilt:")
        for n in PATCHED:
            print("    firmware/%s   %s bytes"
                  % (n, format(os.path.getsize(os.path.join(FW, n)), ",")))
        print("\nNothing has been written to the ONE. That is the next step.")
    pause()


def step_flash():
    if not have(PATCHED):
        print("""
The patched images are not built yet. Do "Build the patched images" first.""")
        return pause()
    if not have(STOCK):
        print("""
Refusing: your original firmware files are missing from firmware/, so you
would have nothing to go back to. Do "Back up my firmware" first.""")
        return pause()

    print("""
This writes the ONE.

What actually happens: the device has two firmware slots and only the one it
is NOT running gets written. Then it is told to start using that slot. If the
new firmware misbehaves, "Go back" switches to the old slot and you are
exactly where you started.

Three things to know before you say yes:

  * Read SAFETY.md. It is short. The one-paragraph version: this is reversible
    through the two slots, but there is no USB rescue if an image both passes
    its checksum and fails to boot, and recovering from that needs opening the
    case.

  * After patching, a long press on the knob while the microphone indicator is
    lit cycles Internal -> External -> External + 48 V. That means a long press
    can switch phantom power ON. Unplug anything on the XLR that must not see
    48 V -- ribbon microphones especially.

  * Do not unplug the ONE while it is writing.
""")
    if ask('Type exactly  patch my one  to go ahead: ') != "patch my one":
        print("\nNot patching. Nothing was written.")
        return pause()

    rc, out = run_capture("usb/onev2_flash.py", "flash",
                          "firmware/" + PATCHED[0], "firmware/" + PATCHED[1], "--yes")
    if rc != 0:
        print("""
The write did not finish cleanly. Nothing was switched over, so the ONE is
still running the firmware it was running before -- check it with "Check my
device" and try again.""")
        return pause()

    m = re.search(r"bank (\d) is written and verified", out)
    if not m:
        print("""
The write reported success but did not say which slot it used, so I will not
guess. Read the output above for the line telling you what to run, or use
"Check my device" and switch slots from there.""")
        return pause()
    target = m.group(1)

    print("""
Written to slot %s and verified against the file. The ONE is still running the
OLD firmware -- the new one is sitting in the other slot, not in use yet.
""" % target)
    if ask("Switch over to the patched firmware now? [Y/n] ", "") == "n":
        print("""
Left alone, and nothing is lost: the patched firmware stays in slot %s until
you switch to it. Choose this menu item again, or run:

    %s usb/onev2_flash.py activate %s""" % (target, os.path.basename(PY), target))
        return pause()

    rc = run("usb/onev2_flash.py", "activate", target)
    if rc == 0:
        print("""
The ONE restarted on the patched firmware. Run the test next.""")
    pause()


def step_test():
    print("""
26 checks the computer makes by itself, then five long presses it asks you to
do while it watches what the device reports.

Phase A2 switches 48 V phantom power on. Unplug the XLR first if anything on
it should not see 48 V.

Stay at the device -- it will ask you to press and hold the knob, and it
decides pass or fail from what the device reports back. Walking away makes it
fail for no good reason.
""")
    if ask("Ready, at the device? [y/N] ", "") != "y":
        return pause()
    run("usb/r9-test.py")
    pause()


def step_rollback():
    print("""
Both firmware slots keep whatever was last written to them, so this just tells
the ONE to start using the other one. It is the undo button.
""")
    now, out = running_bank()
    if now is None:
        print("""
Could not read which slot it is running, so I will not guess. "Check my
device" first.""")
        return pause()
    other = 1 - now
    print("""
It is running slot %d. The other slot is %d, holding whatever was written
there before -- for most people that is the firmware from before the patch.
""" % (now, other))
    if ask("Switch to slot %d? [y/N] " % other, "") != "y":
        print("Cancelled. Nothing changed.")
        return pause()
    run("usb/onev2_flash.py", "activate", other)
    pause()


def step_help():
    print("""
What this is
------------
A patch to the ONE's own firmware. Two parts:

  * its USB description of itself is corrected, so Windows, macOS and an iPad
    all drive it with the drivers they already ship -- no Apogee software;
  * 82 bytes of code are added, so a long press on the knob switches the
    microphone input between Internal, External and External + 48 V, which
    previously only Apogee's app could do.

The order to do things in
-------------------------
  1  Check my device        makes sure the computer can talk to it at all
  2  Back up my firmware    saves what is on your ONE right now. Do not skip.
  3  Build the patched      makes the new firmware from your backup
  4  Flash and switch over  writes it
  5  Test it                proves it worked

  6  Go back                if you do not like it

Steps 1, 2 and 5 only read. Step 3 does not touch the device. Step 4 is the
only one that writes.

What you need
-------------
  * the ONE connected to THIS computer by USB""")
    if WIN:
        print("""  * on Windows, WinUSB bound to the ONE's interface 3 -- one-time, with Zadig.
    "Check my device" tells you if this is missing and how to fix it.""")
    print("""  * the two Python packages the launcher already installed for you

If something goes wrong
-----------------------
"Go back" (menu item 6) fixes almost everything, because the old firmware is
still sitting in the other slot. SAFETY.md covers the rest, including the one
case that is genuinely unrecoverable and how the tools here refuse to cause it.
""")
    pause()


ITEMS = [("1", "Check my device", "reads only", step_check),
         ("2", "Back up my firmware", "reads only -- do this first", step_backup),
         ("3", "Build the patched images", "does not touch the device", step_build),
         ("4", "Flash it and switch over", "WRITES the device", step_flash),
         ("5", "Test it", "reads only, asks you to press the knob", step_test),
         ("6", "Go back to the other firmware slot", "the undo button", step_rollback),
         ("?", "What do I do? Read this first", "", step_help)]


def main():
    while True:
        print("\n" + "=" * 70)
        print("  Apogee ONE (2nd gen) -- driverless firmware patch")
        print("=" * 70)
        s = ("backed up" if have(STOCK) else "NOT backed up yet")
        p = ("built" if have(PATCHED) else "not built")
        print("  your firmware: %s          patched images: %s" % (s, p))
        print("-" * 70)
        for k, label, note, _ in ITEMS:
            print("   %s)  %-34s %s" % (k, label, ("(%s)" % note) if note else ""))
        print("   q)  Quit")
        c = ask("\n  Choose: ", "")
        if c in ("q", "quit", "exit"):
            print()
            return 0
        for k, _, _, fn in ITEMS:
            if c == k:
                fn()
                break
        else:
            if c:
                print("  Not one of the choices.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, Closed):
        print()
        sys.exit(0)
