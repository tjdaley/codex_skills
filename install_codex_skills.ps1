param(
    [switch]$SkipPythonDeps
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Cyan
}

function Confirm-Yes {
    param(
        [string]$Prompt,
        [bool]$DefaultYes = $true
    )

    $suffix = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
    $response = Read-Host "$Prompt $suffix"

    if ([string]::IsNullOrWhiteSpace($response)) {
        return $DefaultYes
    }

    return $response.Trim().ToLowerInvariant().StartsWith("y")
}

$repoRoot = $PSScriptRoot
$skillsTargetRoot = Join-Path $env:USERPROFILE ".codex\skills"

Write-Section "Codex Skills Installer"
Write-Host "Source folder: $repoRoot"
Write-Host "Target folder: $skillsTargetRoot"

if (-not (Test-Path $skillsTargetRoot)) {
    Write-Host "Creating $skillsTargetRoot"
    New-Item -ItemType Directory -Path $skillsTargetRoot | Out-Null
}

$skillDirs = Get-ChildItem -Path $repoRoot -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") }

if (-not $skillDirs) {
    throw "No skill folders were found next to this installer."
}

Write-Section "Skills Found"
$skillDirs | ForEach-Object { Write-Host "- $($_.Name)" }

foreach ($skillDir in $skillDirs) {
    $destination = Join-Path $skillsTargetRoot $skillDir.Name

    if (Test-Path $destination) {
        $replace = Confirm-Yes "Replace existing skill '$($skillDir.Name)'?" $true
        if (-not $replace) {
            Write-Host "Skipping $($skillDir.Name)"
            continue
        }

        Remove-Item -Path $destination -Recurse -Force
    }

    Write-Host "Installing $($skillDir.Name)..."
    Copy-Item -Path $skillDir.FullName -Destination $destination -Recurse
}

if (-not $SkipPythonDeps) {
    $discoverySkill = $skillDirs | Where-Object { $_.Name -eq "discovery-compliance" }
    if ($discoverySkill) {
        $installDeps = Confirm-Yes "Install or update Python packages needed for discovery-compliance?" $true
        if ($installDeps) {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if ($python) {
                & $python.Source -m pip install pypdf openpyxl pymupdf pillow
            } else {
                Write-Warning "Python was not found on PATH. Skipping dependency installation."
            }
        }
    }
}

Write-Section "Done"
Write-Host "The selected skills were installed to $skillsTargetRoot"
Write-Host "Restart Codex to pick up the new or updated skills."

if ($Host.Name -like "*ConsoleHost*") {
    Write-Host ""
    Read-Host "Press Enter to close"
}
