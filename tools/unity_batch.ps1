# Run a static editor method headless in the mod's Unity project and show the log tail.
# Usage: powershell -File tools\unity_batch.ps1 -Method HumanKerbalsBatch.SetupMod [-Editor <path to Unity.exe>]
param(
    [Parameter(Mandatory = $true)] [string] $Method,
    [string] $Editor = "",
    [string] $Project = "",
    [int] $TimeoutMinutes = 60
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Project) { $Project = Join-Path $scriptDir "..\unity" }
$Project = (Resolve-Path $Project).Path
$version = (Get-Content (Join-Path $Project "ProjectSettings\ProjectVersion.txt") | Select-String "m_EditorVersion:").ToString().Split(":")[1].Trim()

if (-not $Editor) {
    $candidates = @(
        "C:\Program Files\Unity\Hub\Editor\$version\Editor\Unity.exe",
        "C:\Program Files\Unity\Editor\$version\Editor\Unity.exe",
        "C:\Program Files\Unity $version\Editor\Unity.exe"
    )
    $Editor = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Editor) { throw "Unity $version not found; pass -Editor" }
}

$logDir = Join-Path $scriptDir "..\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path (Resolve-Path $logDir).Path ("unity_" + ($Method -replace "[^A-Za-z0-9]", "_") + ".log")
if (Test-Path $log) { Remove-Item $log -Force }

# No -quit: the batch entry points call EditorApplication.Exit themselves once their async work settles.
$args = @("-batchmode", "-nographics", "-projectPath", $Project, "-executeMethod", $Method, "-logFile", $log)
Write-Host "Running: $Editor $($args -join ' ')"
$p = Start-Process -FilePath $Editor -ArgumentList $args -WindowStyle Hidden -PassThru
if (-not $p.WaitForExit($TimeoutMinutes * 60 * 1000)) {
    $p.Kill()
    throw "Unity did not finish within $TimeoutMinutes minutes (log: $log)"
}
Write-Host "Exit code: $($p.ExitCode)"
if (Test-Path $log) {
    Write-Host "---- log tail ($log) ----"
    Get-Content $log -Tail 60
    $errors = Select-String -Path $log -Pattern "error CS|Exception|License|Aborting batchmode" | Select-Object -First 20
    if ($errors) { Write-Host "---- notable lines ----"; $errors | ForEach-Object { Write-Host $_.Line } }
}
exit $p.ExitCode
