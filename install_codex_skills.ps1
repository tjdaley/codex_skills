param(
    [string]$RepoUrl = "https://github.com/tjdaley/codex_skills.git",
    [string]$CacheDir = (Join-Path $env:LOCALAPPDATA "CodexSkills\codex_skills"),
    [string]$LocalRepoPath,
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

function Get-SkillDirs {
    param([string]$RootPath)

    return Get-ChildItem -Path $RootPath -Directory |
        Where-Object {
            $_.Name -notlike ".*" -and
            (Test-Path (Join-Path $_.FullName "SKILL.md"))
        } |
        Sort-Object Name
}

function Prompt-SkillSelection {
    param([array]$SkillDirs)

    Write-Host "Type the numbers to install, separated by commas."
    Write-Host "Type 'all' to install every skill."
    Write-Host "Press Enter for all."
    Write-Host ""

    for ($i = 0; $i -lt $SkillDirs.Count; $i++) {
        Write-Host (("{0}. {1}" -f ($i + 1), $SkillDirs[$i].Name))
    }

    Write-Host ""
    $selection = Read-Host "Which skills would you like to install?"

    if ([string]::IsNullOrWhiteSpace($selection) -or $selection.Trim().ToLowerInvariant() -eq "all") {
        return $SkillDirs
    }

    $indexes = @()
    foreach ($part in ($selection -split ',')) {
        $trimmed = $part.Trim()
        if (-not $trimmed) {
            continue
        }

        $parsed = 0
        if (-not [int]::TryParse($trimmed, [ref]$parsed)) {
            throw "Invalid selection '$trimmed'. Use numbers like 1,2 or type all."
        }

        if ($parsed -lt 1 -or $parsed -gt $SkillDirs.Count) {
            throw "Selection '$trimmed' is out of range."
        }

        $indexes += ($parsed - 1)
    }

    if (-not $indexes) {
        throw "No valid skills were selected."
    }

    return $indexes |
        Select-Object -Unique |
        ForEach-Object { $SkillDirs[$_] }
}

function Update-RepoCache {
    param(
        [string]$RepoUrl,
        [string]$CacheDir
    )

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        throw "Git was not found. Please install Git or use -LocalRepoPath."
    }

    $cacheParent = Split-Path -Parent $CacheDir
    if (-not (Test-Path $cacheParent)) {
        New-Item -ItemType Directory -Path $cacheParent -Force | Out-Null
    }

    if (-not (Test-Path $CacheDir)) {
        Write-Host "Cloning repository to $CacheDir"
        & $git.Source clone $RepoUrl $CacheDir
    } else {
        Write-Host "Refreshing repository in $CacheDir"
        & $git.Source -C $CacheDir pull --ff-only
    }

    return $CacheDir
}

$skillsTargetRoot = Join-Path $env:USERPROFILE ".codex\skills"

Write-Section "Codex Skills Installer"
Write-Host "Target folder: $skillsTargetRoot"

$repoRoot = $null
if ($LocalRepoPath) {
    if (-not (Test-Path $LocalRepoPath)) {
        throw "Local repo path not found: $LocalRepoPath"
    }

    $repoRoot = (Resolve-Path $LocalRepoPath).Path
    Write-Host "Using local repository folder: $repoRoot"
} else {
    Write-Host "Repository URL: $RepoUrl"
    $repoRoot = Update-RepoCache -RepoUrl $RepoUrl -CacheDir $CacheDir
}

if (-not (Test-Path $skillsTargetRoot)) {
    Write-Host "Creating $skillsTargetRoot"
    New-Item -ItemType Directory -Path $skillsTargetRoot | Out-Null
}

$skillDirs = Get-SkillDirs -RootPath $repoRoot
if (-not $skillDirs) {
    throw "No skill folders were found in $repoRoot"
}

Write-Section "Available Skills"
$selectedSkills = Prompt-SkillSelection -SkillDirs $skillDirs

Write-Section "Installing Skills"
foreach ($skillDir in $selectedSkills) {
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
    $needsDiscoveryDeps = $selectedSkills | Where-Object { $_.Name -eq "discovery-compliance" }
    if ($needsDiscoveryDeps) {
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
Write-Host "Installed skills were copied to $skillsTargetRoot"
Write-Host "Restart Codex to pick up the new or updated skills."

if ($Host.Name -like "*ConsoleHost*") {
    Write-Host ""
    Read-Host "Press Enter to close"
}
