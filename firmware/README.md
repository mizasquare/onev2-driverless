# Put your own firmware images here

This directory is intentionally empty. The two images are Apogee's property and are not
redistributed with this project.

```
ONEv2_USB_Audio_Image0.bin    98,488 bytes
ONEv2_USB_Audio_Image1.bin   229,560 bytes
```

Both come out of `One Firmware Updater.app` inside Apogee's **Maestro 2.5C** package for the ONE
(`One iPad & Mac 2.5C.dmg`), available from Apogee's support pages. Extract the two files and drop
them here.

`../patch/patch_r9.py` reads them, writes `*.R9.patched.bin` beside them, and refuses to write
anything if the fingerprints it checks do not match — so a wrong or newer image fails loudly rather
than producing a bad flash.
