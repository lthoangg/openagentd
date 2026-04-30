<#
.SYNOPSIS
    One-command installer for openagentd on Windows.

.DESCRIPTION
    Mirrors install.sh:
        1. Ensure uv is available (bootstrap from astral.sh/uv if missing).
        2. Run `uv tool install openagentd` so `openagentd` lands on PATH.
        3. Print next-step hint (`openagentd` auto-runs first-time setup).

    The official uv installer for Windows lives at
    https://astral.sh/uv/install.ps1 and installs to
    %USERPROFILE%\.local\bin which uv adds to user PATH.

.PARAMETER Dev
    Install from GitHub main instead of PyPI. Useful before the package
    has been published.

.PARAMETER Version
    Pin a specific PyPI version (e.g. "0.2.0"). Ignored when -Dev is set.

.EXAMPLE
    iwr https://raw.githubusercontent.com/lthoangg/openagentd/main/install.ps1 -useb | iex

.EXAMPLE
    .\install.ps1 -Dev

.EXAMPLE
    .\install.ps1 -Version 0.2.0
#>

[CmdletBinding()]
param(
    [switch] $Dev,
    [string] $Version
)

# Stop on any non-handled error so a half-finished install can't masquerade
# as success — matches `set -e` in install.sh.
$ErrorActionPreference = 'Stop'

$Repo    = 'lthoangg/openagentd'
$Package = 'openagentd'

# ── pretty output ──────────────────────────────────────────────────────────
function Write-Step([string] $Message) {
    Write-Host '==> ' -NoNewline -ForegroundColor Green
    Write-Host $Message
}

function Write-Note([string] $Message) {
    Write-Host $Message -ForegroundColor DarkGray
}

# ── 1. uv ──────────────────────────────────────────────────────────────────
function Test-UvOnPath {
    return [bool] (Get-Command uv -ErrorAction SilentlyContinue)
}

function Install-Uv {
    if (Test-UvOnPath) { return }

    Write-Step "Installing uv (Python package manager)"
    Write-Note "    Source: https://astral.sh/uv/install.ps1"

    # The official installer is itself a PS script; download then execute
    # rather than piping straight into iex so a partial transfer can't run.
    $tempScript = [System.IO.Path]::GetTempFileName() + '.ps1'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://astral.sh/uv/install.ps1' -OutFile $tempScript
        & powershell -ExecutionPolicy Bypass -File $tempScript
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $tempScript
    }

    # The installer adds ~/.local/bin to user PATH, but the current process
    # doesn't pick that up automatically — refresh PATH from the registry.
    $userPath    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $env:Path = "$machinePath;$userPath"

    if (-not (Test-UvOnPath)) {
        Write-Error @"
uv was installed but is not on PATH for this shell.
Open a new PowerShell window and re-run this script, or add
%USERPROFILE%\.local\bin to PATH manually.
"@
        exit 1
    }
}

# ── 2. install openagentd via uv tool ──────────────────────────────────────
function Install-Openagentd {
    if ($Dev) {
        $spec = "git+https://github.com/$Repo@main"
        Write-Step "Installing $Package from $Repo@main"
    } elseif ($Version) {
        $spec = "$Package==$Version"
        Write-Step "Installing $spec from PyPI"
    } else {
        $spec = $Package
        Write-Step "Installing $Package from PyPI"
    }

    & uv tool install --force $spec
    if ($LASTEXITCODE -ne 0) {
        Write-Error "uv tool install exited with code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

# ── 3. report ──────────────────────────────────────────────────────────────
function Write-Report {
    Write-Host ''
    Write-Step 'Installed!'

    $openagentd = Get-Command openagentd -ErrorAction SilentlyContinue
    if ($openagentd) {
        $version = (& openagentd --version 2>$null) -join ' '
        if (-not $version) { $version = 'unknown' }
        Write-Note "    openagentd $version"
    } else {
        Write-Warning @"
'openagentd' is not on PATH for this shell.
Open a new PowerShell window, or add %USERPROFILE%\.local\bin to PATH.
"@
    }

    Write-Host ''
    Write-Host 'Next: run ' -NoNewline
    Write-Host 'openagentd' -ForegroundColor White -NoNewline
    Write-Host ' to launch the server.'
    Write-Note '      First run walks you through provider + model selection.'
    Write-Host ''
}

Install-Uv
Install-Openagentd
Write-Report
