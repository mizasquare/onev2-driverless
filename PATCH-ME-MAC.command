#!/bin/bash
# Double-click this in Finder. It finds Python, installs the two packages the tools need into a
# private folder inside this one, and opens the menu. It does not need your password.
# Nothing here writes to the ONE on its own -- the menu asks first.
#
# If Finder says it cannot be opened because it is from an unidentified developer:
# right-click the file, choose Open, then Open again. That happens to anything downloaded
# rather than cloned, and only the first time.

cd "$(dirname "$0")" || exit 1
VENV="$PWD/.venv"
VPY="$VENV/bin/python3"

echo
echo "  Apogee ONE -- driverless firmware patch"
echo "  ======================================="
echo

hold() { echo; printf "  Press Enter to close this window. "; read -r _; }

if [ -x "$VPY" ]; then
    exec "$VPY" tools/menu.py
fi

# ------------------------------------------------------------------ find a Python
PY=""
for c in python3 python3.13 python3.12 python3.11 python3.10 python3.9 /usr/bin/python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys, venv' >/dev/null 2>&1; then
        PY="$c"
        break
    fi
done

if [ -z "$PY" ]; then
    cat <<'EOF'
  Python is not usable on this Mac yet, and the tools here are written in
  Python. macOS ships it, but only once the command line tools are present.

  A window should appear asking to install them. Say yes; it takes a few
  minutes and installs nothing else.

  If no window appears, run this in Terminal:

      xcode-select --install

  Then double-click PATCH-ME-MAC.command again.
EOF
    xcode-select --install 2>/dev/null
    hold
    exit 1
fi

echo "  Using $("$PY" -V 2>&1) at $(command -v "$PY")"
echo
echo "  Setting up, once. This makes a folder called .venv inside this one and"
echo "  puts two USB packages in it. Your system Python is left alone."
echo

"$PY" -m venv "$VENV" || {
    echo
    echo "  Could not create the .venv folder here. If this project sits in"
    echo "  iCloud Drive, copy it to somewhere like ~/onev2 and try again."
    hold
    exit 1
}

"$VPY" -m pip install --upgrade pip --quiet --disable-pip-version-check 2>/dev/null
echo "  Installing pyusb and libusb-package..."
if ! "$VPY" -m pip install --quiet --disable-pip-version-check pyusb libusb-package; then
    echo
    echo "  Could not download the USB packages. That is almost always no"
    echo "  internet, or a proxy blocking it. The two needed are pyusb and"
    echo "  libusb-package."
    hold
    exit 1
fi

echo "  Installing sounddevice and numpy, used by the test..."
"$VPY" -m pip install --quiet --disable-pip-version-check sounddevice numpy 2>/dev/null

# libusb-package ships a prebuilt libusb for macOS, but check rather than assume.
if ! "$VPY" -c 'import libusb_package; assert libusb_package.get_libusb1_backend()' 2>/dev/null; then
    echo
    echo "  pyusb installed, but it cannot find a working libusb. Install one:"
    echo
    echo "      brew install libusb"
    echo
    echo "  then double-click PATCH-ME-MAC.command again. If you do not have"
    echo "  Homebrew, https://brew.sh has the one-line installer."
    hold
    exit 1
fi

echo
echo "  Ready."
exec "$VPY" tools/menu.py
