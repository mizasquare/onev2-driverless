# What Windows currently thinks the ONE is, and what to do about it.
# Read-only. Changes nothing. Run it by hand, or let the menu's "Check my device" call it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\win-usb-state.ps1

$ErrorActionPreference = 'SilentlyContinue'
$ID = '*VID_0C60&PID_0017*'

function Nodes($presentOnly) {
    $q = if ($presentOnly) { Get-PnpDevice -PresentOnly } else { Get-PnpDevice }
    $q | Where-Object { $_.InstanceId -like $ID } | ForEach-Object {
        [pscustomobject]@{
            Status  = $_.Status
            Service = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Service').Data
            Problem = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode').Data
            Id      = $_.InstanceId
        }
    }
}

$present = @(Nodes $true)

Write-Output ""
Write-Output "Apogee ONE -- what Windows sees right now"
Write-Output "========================================="
Write-Output ""

if (-not $present) {
    Write-Output "  Nothing. The ONE is not plugged into this computer, or the cable is"
    Write-Output "  charge-only and carries no data. Try another cable and another port."
    Write-Output ""
    exit 2
}

foreach ($n in $present) {
    $what = switch -Wildcard ($n.Id) {
        '*&MI_00*' { 'interfaces 0-2, the sound card' }
        '*&MI_03*' { 'interface 3, the control channel we flash through' }
        default    { 'the whole device (composite parent)' }
    }
    $line = "  {0,-8} driver={1,-10} problem={2,-3}  {3}" -f $n.Status, $n.Service, $n.Problem, $what
    Write-Output $line
}
Write-Output ""

$parent = $present | Where-Object { $_.Id -notlike '*&MI_*' }
$mi00   = $present | Where-Object { $_.Id -like '*&MI_00*' }
$mi03   = $present | Where-Object { $_.Id -like '*&MI_03*' }

# ---------------------------------------------------------------- diagnose
if ($parent.Service -eq 'WinUSB') {
    Write-Output "  WinUSB owns the WHOLE device."
    Write-Output ""
    Write-Output "  Flashing works. Audio does not, and will not, because no audio driver"
    Write-Output "  can load while WinUSB holds the parent. This is the right state for"
    Write-Output "  patching a device that is still on factory firmware, and the wrong"
    Write-Output "  state to leave it in afterwards."
    Write-Output ""
    Write-Output "  When you have finished patching, give the device back to Windows:"
    Write-Output "    1. Device Manager -> Universal Serial Bus devices -> ONEv2"
    Write-Output "    2. right-click -> Uninstall device"
    Write-Output "    3. tick 'Attempt to remove the driver for this device' -> Uninstall"
    Write-Output "    4. unplug and replug"
    exit 0
}

if ($mi03 -and $mi03.Service -eq 'WinUSB') {
    if ($mi00 -and $mi00.Problem -eq 0) {
        Write-Output "  Everything is as it should be: the sound card is driven by Windows'"
        Write-Output "  own driver, and the control channel is reachable for flashing."
        exit 0
    }
    Write-Output "  Flashing works. The sound card is not starting (problem $($mi00.Problem))."
    Write-Output "  On factory firmware that is expected -- it is what the patch fixes."
    exit 0
}

if ($mi03) {
    Write-Output "  The control channel is there but Windows has '$($mi03.Service)' on it, not"
    Write-Output "  WinUSB, so nothing here can talk to the device."
    Write-Output ""
    Write-Output "  Fix: run Zadig (https://zadig.akeo.ie/) as Administrator,"
    Write-Output "    Options -> List All Devices,"
    Write-Output "    pick 'iAP Interface (Interface 3)',"
    Write-Output "    choose WinUSB, press Install."
    Write-Output ""
    Write-Output "  Pick interface 3 and nothing else. Interface 0 is the sound card."
    exit 1
}

# No MI_03 at all.
Write-Output "  There is no separate node for interface 3, so there is nothing for WinUSB"
Write-Output "  to attach to."
Write-Output ""
Write-Output "  That is what factory firmware looks like on Windows: its descriptor claims"
Write-Output "  interfaces 0-3 are all one audio function, so Windows makes a single child"
Write-Output "  for the lot and loads the audio driver on it -- which then fails, because"
Write-Output "  interface 3 is not audio. Hence 'problem 10' above, if you see it."
Write-Output ""
Write-Output "  To patch from this computer, hand the WHOLE device to WinUSB instead:"
Write-Output "    1. run Zadig (https://zadig.akeo.ie/) as Administrator"
Write-Output "    2. Options -> List All Devices"
Write-Output "    3. Options -> UNTICK 'Ignore Hubs or Composite Parents'   <- the step"
Write-Output "       everyone misses; without it the parent is not in the list"
Write-Output "    4. pick 'ONEv2 (Composite Parent)' -- USB ID 0C60 0017, no interface"
Write-Output "       number after it"
Write-Output "    5. driver WinUSB -> Replace Driver, and accept the system-driver warning"
Write-Output ""
Write-Output "  Audio stays dead while that binding is in place -- it is already dead on"
Write-Output "  factory firmware anyway. Undo it after patching, as this script will then"
Write-Output "  tell you."
exit 1
