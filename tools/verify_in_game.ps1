# Launch KSP2 Redux with the Human Kerbals mod and watch the log.
#
#   powershell -File tools\verify_in_game.ps1                 # startup check: registration + post-init lines, then close
#   powershell -File tools\verify_in_game.ps1 -TestLoad       # plugin test mode: auto-load the newest save, dump kerbal
#                                                             # portraits to logs\portraits, quit when done
#   powershell -File tools\verify_in_game.ps1 -MissionControl # as -TestLoad, then enter Mission Control and save
#                                                             # screenshots of the converted actors to logs\missioncontrol
#   powershell -File tools\verify_in_game.ps1 -AudioTest      # from the main menu, post the remapped narration events
#                                                             # and print what Wwise reports (AUDIO: lines), then quit
param(
    [int] $TimeoutMinutes = 6,
    [switch] $KeepRunning,
    [switch] $TestLoad,
    [switch] $MissionControl,
    [switch] $AudioTest,
    [string] $Save = ""
)
$ErrorActionPreference = "Stop"
$ksp = "C:\Program Files (x86)\Steam\steamapps\common\Kerbal Space Program 2"
$exe = Join-Path $ksp "KSP2_x64.exe"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$portraitDir = Join-Path (Resolve-Path (Join-Path $scriptDir "..")).Path "logs\portraits"
$mcDir = Join-Path (Resolve-Path (Join-Path $scriptDir "..")).Path "logs\missioncontrol"
if ($MissionControl) { $TestLoad = $true }
$start = Get-Date

$running = Get-Process KSP2_x64 -ErrorAction SilentlyContinue
if ($running) { throw "KSP2 is already running (pid $($running.Id)); close it first." }

$args = @()
if ($TestLoad) {
    if (-not $Save) {
        $savesRoot = Join-Path $env:USERPROFILE "AppData\LocalLow\Intercept Games\Kerbal Space Program 2\Saves\SinglePlayer"
        $Save = Get-ChildItem -Path $savesRoot -Recurse -Filter "*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $Save) { throw "No save file found to load." }
    if (Test-Path $portraitDir) { Remove-Item $portraitDir -Recurse -Force }
    New-Item -ItemType Directory -Force $portraitDir | Out-Null
    $args = @("-humankerbals-test", "-humankerbals-load", "`"$Save`"", "-humankerbals-portraits", "`"$portraitDir`"")
    if ($TimeoutMinutes -lt 12) { $TimeoutMinutes = 12 }
    if ($MissionControl) {
        if (Test-Path $mcDir) { Remove-Item $mcDir -Recurse -Force }
        New-Item -ItemType Directory -Force $mcDir | Out-Null
        $args += @("-humankerbals-missioncontrol", "`"$mcDir`"")
        if ($TimeoutMinutes -lt 15) { $TimeoutMinutes = 15 }
    }
    Write-Host "Test mode: loading $Save"
}
elseif ($AudioTest) {
    $args = @("-humankerbals-test", "-humankerbals-audiotest")
    if ($TimeoutMinutes -lt 8) { $TimeoutMinutes = 8 }
    Write-Host "Audio test mode"
}

if ($args.Count -gt 0) {
    $proc = Start-Process -FilePath $exe -WorkingDirectory $ksp -ArgumentList $args -WindowStyle Hidden -PassThru
}
else {
    $proc = Start-Process -FilePath $exe -WorkingDirectory $ksp -WindowStyle Hidden -PassThru
}
Write-Host "Started KSP2 (pid $($proc.Id)); watching logs for up to $TimeoutMinutes minutes..."

$patterns = "Registered plugin: HumanKerbals|\[HumanKerbals|HumanKerbals\.dll|Harmony|error|Error|Exception|Found Space Warp plugin at|Loading addressables for Human|ReSkin|ReParent|failed to find|Kerbal3DModel|AttachToNamedParent|Portrait|AUDIO:|oundbank|Wwise"
$deadline = $start.AddMinutes($TimeoutMinutes)
$log = $null
$seenRegistered = $false
$seenPostInit = $false
$seenTestDone = $false
$settleUntil = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $log = Get-ChildItem -Path $ksp -Filter "Ksp2*.log" | Where-Object { $_.LastWriteTime -gt $start } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log) {
        $text = Get-Content $log.FullName -Raw -ErrorAction SilentlyContinue
        if ($text -match "Registered plugin: HumanKerbals") { $seenRegistered = $true }
        if ($text -match "Post-initialization for plugin Human Kerbals completed|\[HumanKerbals\] Active:") { $seenPostInit = $true }
        if ($text -match "\[HumanKerbals\] TEST: done") { $seenTestDone = $true }
        if (-not $TestLoad -and -not $AudioTest) {
            if ($seenPostInit -and -not $settleUntil) { $settleUntil = (Get-Date).AddSeconds(15) }
            if ($settleUntil -and (Get-Date) -gt $settleUntil) { break }
        }
        elseif ($seenTestDone -and -not $settleUntil) { $settleUntil = (Get-Date).AddSeconds(10) }
        if ($settleUntil -and (Get-Date) -gt $settleUntil) { break }
        if ($text -match "Initialization for plugin Human Kerbals.*failed") { break }
    }
    if ($proc.HasExited) { Write-Host "Game exited with code $($proc.ExitCode)"; break }
}

if ($log) {
    Write-Host "---- $($log.Name): matching lines ----"
    Select-String -Path $log.FullName -Pattern $patterns | ForEach-Object { $_.Line } |
        Where-Object { $_ -notmatch "PropertyWatcher|ERR 00:00|VideoPlayer|Discord|PlumeManager|OTA Content|iBoxDB|Backtrace" } |
        Select-Object -First 120 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "No new Ksp2*.log appeared."
}

if (-not $KeepRunning -and -not $proc.HasExited) {
    Write-Host "Closing the game."
    Stop-Process -Id $proc.Id -Force
}
if ($TestLoad) {
    $pngs = @(Get-ChildItem -Path $portraitDir -Filter "*.png" -ErrorAction SilentlyContinue)
    Write-Host "Portraits written: $($pngs.Count) -> $portraitDir"
    $pngs | Select-Object -First 20 | ForEach-Object { Write-Host "  $($_.Name) ($([int]($_.Length/1KB)) KB)" }
}
if ($MissionControl) {
    $shots = @(Get-ChildItem -Path $mcDir -Filter "*.png" -ErrorAction SilentlyContinue)
    Write-Host "Mission Control screenshots: $($shots.Count) -> $mcDir"
    $shots | ForEach-Object { Write-Host "  $($_.Name) ($([int]($_.Length/1KB)) KB)" }
}
if ($seenRegistered -and $seenPostInit) { Write-Host "RESULT: HumanKerbals registered and post-initialized." }
elseif ($seenRegistered) { Write-Host "RESULT: HumanKerbals registered but post-initialization was not seen." }
else { Write-Host "RESULT: HumanKerbals NOT registered." }
