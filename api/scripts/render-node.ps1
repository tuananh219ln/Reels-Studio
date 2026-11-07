# Run this computer as a Reels Studio render machine (docs/deployment.md, "Render machine").
#
#   powershell -ExecutionPolicy Bypass -File api\scripts\render-node.ps1 -Server https://reels.example.com -Token <token>
#
# The first run installs what it needs: a Python 3.12 venv in api\.venv with the api and the render core, and (for
# "Cảnh động") HyperFrames and GSAP in %LOCALAPPDATA%\reels-hyperframes. FFmpeg must already be on PATH (winget install
# Gyan.FFmpeg). The token is shown once when the machine is added on Cài đặt › Máy render; it is passed through the
# environment, never written to a file. Ctrl+C stops the machine; a job it was rendering goes back to the queue.
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Token,
    [switch]$SkipMotion
)
$ErrorActionPreference = "Stop"
$api = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $api
$python = Join-Path $api ".venv\Scripts\python.exe"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $winget = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($winget) { $env:PATH = "$($winget.DirectoryName);$env:PATH" }
    else { throw "Không tìm thấy FFmpeg: chạy 'winget install Gyan.FFmpeg' rồi mở lại PowerShell" }
}

if (-not (Test-Path $python)) {
    Write-Host "Tạo môi trường Python 3.12 trong api\.venv ..."
    py -3.12 -m venv (Join-Path $api ".venv")
}
Write-Host "Cài / cập nhật Reels Studio (api và render core) ..."
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet (Join-Path $repo "worker") $api

if (-not $SkipMotion) {
    $hf = Join-Path $env:LOCALAPPDATA "reels-hyperframes"
    if (-not (Test-Path (Join-Path $hf "node_modules\gsap\dist\gsap.min.js"))) {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "Cảnh động cần Node 22 (winget install OpenJS.NodeJS.LTS), hoặc chạy lại với -SkipMotion"
        }
        Write-Host "Cài HyperFrames và GSAP cho cảnh động ..."
        New-Item -ItemType Directory -Force -Path $hf | Out-Null
        Push-Location $hf
        npm init -y | Out-Null
        npm install --no-fund --no-audit hyperframes@0.9.19 gsap@3.15.0
        npx hyperframes browser ensure
        Pop-Location
    }
    $env:PATH = "$(Join-Path $hf 'node_modules\.bin');$env:PATH"
    $env:HYPERFRAMES_NO_UPDATE_CHECK = "1"; $env:HYPERFRAMES_NO_TELEMETRY = "1"; $env:DO_NOT_TRACK = "1"
}

$env:REELS_SERVER = $Server
$env:REELS_NODE_TOKEN = $Token
Write-Host "Máy render đang chạy. Ctrl+C để dừng."
& $python -m reels_api node
