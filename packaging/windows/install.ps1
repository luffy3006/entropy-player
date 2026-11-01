$ErrorActionPreference = "Stop"

$mpvDirectory = $env:MPV_HOME
$candidateDirectories = @()
if ($mpvDirectory) {
    $candidateDirectories += $mpvDirectory
}
$candidateDirectories += @(
    (Join-Path $env:ProgramFiles "mpv"),
    (Join-Path $env:LOCALAPPDATA "Programs\mpv")
)
$candidateDirectories += $env:PATH -split [IO.Path]::PathSeparator
$mpvDirectory = $candidateDirectories |
    Where-Object { $_ -and (Test-Path (Join-Path $_ "mpv-2.dll")) } |
    Select-Object -First 1
if (-not $mpvDirectory) {
    throw "mpv-2.dll was not found. Install a Windows mpv build, then set MPV_HOME to the folder containing mpv-2.dll."
}

$wheel = Get-ChildItem -Path $PSScriptRoot -Filter "entropy_player-*.whl" |
    Select-Object -First 1
if (-not $wheel) {
    throw "The Entropy Player wheel must be beside install.ps1. Download and extract the Windows release archive first."
}
if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw "Python 3.10 or newer with the Windows Python launcher is required."
}

$env:MPV_HOME = $mpvDirectory
$env:PATH = "$mpvDirectory;$env:PATH"
[Environment]::SetEnvironmentVariable("MPV_HOME", $mpvDirectory, "User")
py.exe -3 -m pip install --user $wheel.FullName

$pyLauncher = Get-Command pyw.exe -ErrorAction SilentlyContinue
if (-not $pyLauncher) {
    throw "The package was installed, but pyw.exe is missing. Repair the Python installation and run install.ps1 again."
}
$installDirectory = Join-Path $env:LOCALAPPDATA "EntropyPlayer"
New-Item -ItemType Directory -Force -Path $installDirectory | Out-Null
$launcherScript = Join-Path $installDirectory "launch.ps1"
$escapedMpvDirectory = $mpvDirectory.Replace("'", "''")
$escapedPyLauncher = $pyLauncher.Source.Replace("'", "''")
@"
`$env:MPV_HOME = '$escapedMpvDirectory'
& '$escapedPyLauncher' -3 -m entropy --gui
"@ | Set-Content -Encoding utf8 -Path $launcherScript

$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Entropy Player"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $startMenu "Entropy Player.lnk"))
$shortcut.TargetPath = (Get-Process -Id $PID).Path
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcherScript`""
$shortcut.WorkingDirectory = $env:USERPROFILE
$shortcut.Save()

Write-Host "Entropy Player was installed. If mpv is not on PATH, set MPV_HOME to $mpvDirectory before launching."
