# idle-watch.ps1 — is the ~9 s hardware watchdog biting when nothing is using the device?
#
# PASSIVE ON PURPOSE. It never opens the device over USB, because our own EP0 traffic would feed
# the watchdog and invalidate the very thing being measured. It only reads Windows-side state:
# the PnP nodes, the audio endpoints, and the usbaudio2 event log.
#
# If the watchdog were firing, the device would reset roughly every 9 s, which means constant
# re-enumeration: usbaudio2 would re-bind and log fresh events, and the endpoints would flap.
# A clean run of ~11 minutes with no new events and problem=0 throughout means it is not biting.

$log = Join-Path $PSScriptRoot "idle-watch.log"
$start = Get-Date
"=== idle watchdog test started $start ===" | Out-File $log -Encoding utf8
"(passive: no USB access from this script)" | Out-File $log -Append -Encoding utf8

$prevEventCount = 0
for ($i = 0; $i -lt 23; $i++) {
    $now = Get-Date
    $elapsed = [int]($now - $start).TotalSeconds

    $nodes = @()
    foreach ($d in (Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_0C60' })) {
        $p = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction SilentlyContinue).Data
        $nodes += ("{0}=problem{1}/{2}" -f ($d.FriendlyName -replace ' ', ''), $p, $d.Status)
    }

    $eps = (Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
            Where-Object { $_.FriendlyName -match 'ONEv2' -and $_.Status -eq 'OK' }).Count

    $ev = 0; $newest = '-'
    try {
        $all = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='usbaudio2'; StartTime=$start} -ErrorAction Stop
        $ev = $all.Count
        $newest = "{0:HH:mm:ss}/Id{1}" -f $all[0].TimeCreated, $all[0].Id
    } catch { }

    $delta = $ev - $prevEventCount
    $prevEventCount = $ev

    $line = "{0:HH:mm:ss}  +{1,4}s  endpointsOK={2}  usbaudio2events_total={3} (+{4})  newest={5}  {6}" -f `
        $now, $elapsed, $eps, $ev, $delta, $newest, ($nodes -join '  ')
    $line | Out-File $log -Append -Encoding utf8

    if ($i -lt 22) { Start-Sleep -Seconds 30 }
}

"=== finished $(Get-Date) ===" | Out-File $log -Append -Encoding utf8
$total = $prevEventCount
if ($total -eq 0) {
    "VERDICT: no usbaudio2 events in the whole window -> the watchdog is NOT resetting the device while idle." |
        Out-File $log -Append -Encoding utf8
} else {
    "VERDICT: $total usbaudio2 events appeared during the idle window -> something is still cycling; inspect the timing gaps." |
        Out-File $log -Append -Encoding utf8
}
Get-Content $log
