# verdict.ps1 — one command that answers "did this firmware round work?"
#
# Reports, for the Apogee ONEv2:
#   1. every PnP node of the device and its problem code  (10 = driver failed to start)
#   2. the inbox usbaudio2 driver's own verdict from the event log (Event ID 34 =
#      "descriptor not compliant or not supported"), newest first
#   3. how many Event-34s fired in the last 2 minutes — several, seconds apart, means the
#      device is re-enumerating in a loop, which is how the ~9 s watchdog would look
#   4. the live config descriptor, read straight off the device (needs the WinUSB bind)
#
# No elevation needed. Run after each flash.

$ErrorActionPreference = 'Continue'
$pid_filter = 'VID_0C60'

Write-Host "=== device nodes ===" -ForegroundColor Cyan
Get-PnpDevice | Where-Object { $_.InstanceId -match $pid_filter } | ForEach-Object {
    $prob = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction SilentlyContinue).Data
    $svc  = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Service'     -ErrorAction SilentlyContinue).Data
    $verdict = switch ($prob) {
        0       { 'OK' }
        10      { 'FAILED_START  <-- driver rejected the device' }
        28      { 'no driver installed' }
        $null   { '' }
        default { "problem $prob" }
    }
    "{0,-26} {1,-12} {2}" -f $_.FriendlyName, $svc, $verdict
}

Write-Host "`n=== usbaudio2 verdict (Event ID 34) ===" -ForegroundColor Cyan
$ev = @()
try {
    $ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='usbaudio2'; Id=34} -MaxEvents 12 -ErrorAction Stop
} catch { Write-Host "  (no usbaudio2 Event 34 in the log at all — that is what success looks like)" }
if ($ev.Count) {
    $ev | Select-Object -First 6 | ForEach-Object {
        "  {0:yyyy-MM-dd HH:mm:ss}  {1}" -f $_.TimeCreated, ($_.Message -replace '\s+', ' ')
    }
    $age = (Get-Date) - $ev[0].TimeCreated
    "`n  newest is {0:N0} s old" -f $age.TotalSeconds
    $recent = $ev | Where-Object { $_.TimeCreated -gt (Get-Date).AddMinutes(-2) }
    "  Event-34s in the last 2 min: {0}" -f $recent.Count
    if ($recent.Count -ge 3) {
        $gaps = @()
        for ($i = 0; $i -lt $recent.Count - 1; $i++) {
            $gaps += [math]::Round(($recent[$i].TimeCreated - $recent[$i+1].TimeCreated).TotalSeconds, 1)
        }
        "  gaps between them (s): {0}" -f ($gaps -join ', ')
        Write-Host "  >> repeated binds seconds apart = the device is re-enumerating in a loop." -ForegroundColor Yellow
    }
}

Write-Host "`n=== live descriptor (needs the WinUSB bind on MI_03) ===" -ForegroundColor Cyan
# Use the project virtualenv rather than the system Python.
$py = Join-Path $PSScriptRoot "..\..\..\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py "$PSScriptRoot\onev2_flash.py" probe --save-config "$PSScriptRoot\live-config.bin" 2>&1 |
    Select-Object -First 45 | ForEach-Object { "  $_" }
