[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Distro = "Ubuntu",
    [string]$SourceRoot = (Get-Location).Path,
    [string]$DestinationRoot = "~/projects",
    [switch]$InstallMissing,
    [switch]$MigrateRepositories,
    [switch]$IncludeNestedRepositories,
    [switch]$SkipDockerCheck
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "==> $Message"
}

function Invoke-Wsl {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $output = & wsl.exe -d $Distro -- @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed ($LASTEXITCODE): $($Arguments -join ' ')`n$output"
    }
    return $output
}

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-GitValue([string]$Repository, [string[]]$Arguments) {
    $result = & git -C $Repository @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return (($result -join "`n").Trim())
}

function Convert-ToWslPath([string]$WindowsPath) {
    $resolved = (Resolve-Path $WindowsPath).Path
    if ($resolved -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = $Matches[2] -replace '\\', '/'
        return "/mnt/$drive/$rest"
    }

    throw "Unsupported Windows path for WSL conversion: '$resolved'. Expected a local drive-letter path such as C:\\Projects\\repo."
}

function Resolve-WslDestinationRoot {
    if ($DestinationRoot.StartsWith("/")) { return $DestinationRoot }

    $wslHome = ((Invoke-Wsl -Arguments @("sh", "-lc", 'printf %s "$HOME"')) -join "`n").Trim()
    if (-not $wslHome) {
        throw "Could not resolve the WSL home directory for '$Distro'. Supply -DestinationRoot with an absolute Linux path such as /home/<user>/projects."
    }

    if ($DestinationRoot -eq "~") { return $wslHome }
    if ($DestinationRoot.StartsWith("~/")) {
        return "$wslHome/$($DestinationRoot.Substring(2))"
    }
    throw "DestinationRoot must be an absolute Linux path or start with ~/ (received '$DestinationRoot')."
}

function Get-RepositoryCandidates([string]$Root) {
    $resolved = (Resolve-Path $Root).Path
    $items = New-Object System.Collections.Generic.List[string]

    if (Test-Path (Join-Path $resolved ".git")) {
        $items.Add($resolved)
    }

    $children = Get-ChildItem -Path $resolved -Directory -Force
    foreach ($child in $children) {
        if (Test-Path (Join-Path $child.FullName ".git")) {
            $items.Add($child.FullName)
        }
    }

    if ($IncludeNestedRepositories) {
        Get-ChildItem -Path $resolved -Directory -Force -Recurse -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName ".git") } |
            ForEach-Object { $items.Add($_.FullName) }
    }

    return $items | Sort-Object -Unique
}

if (-not [System.Environment]::OSVersion.Platform.ToString().StartsWith("Win")) {
    throw "This tool must be run from Windows PowerShell or PowerShell on Windows."
}

Write-Step "Checking WSL2"
if (-not (Test-Command "wsl.exe")) {
    if (-not $InstallMissing) {
        throw "WSL is not available. Re-run with -InstallMissing from an elevated PowerShell session."
    }
    & wsl.exe --install -d $Distro
    throw "WSL installation was requested. If Windows asks for a restart, restart first, complete the $Distro first-run setup, then run this command again."
}

& wsl.exe --set-default-version 2 | Out-Null
$distroNames = (& wsl.exe -l -q 2>$null) -replace "`0", "" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if ($distroNames -notcontains $Distro) {
    if (-not $InstallMissing) {
        throw "WSL distro '$Distro' is not installed. Re-run with -InstallMissing."
    }
    & wsl.exe --install -d $Distro
    throw "Installation of '$Distro' was requested. Complete its first-run setup, then run this command again."
}

$versionLines = (& wsl.exe -l -v 2>$null) -replace "`0", ""
$distroLine = $versionLines | Where-Object { $_ -match "\b$([regex]::Escape($Distro))\b" } | Select-Object -First 1
if ($distroLine -and $distroLine -match "\s1\s*$") {
    if (-not $InstallMissing) {
        throw "'$Distro' is using WSL1. Re-run with -InstallMissing to convert it to WSL2."
    }
    & wsl.exe --set-version $Distro 2
    if ($LASTEXITCODE -ne 0) { throw "Failed to convert '$Distro' to WSL2." }
}

Write-Step "Checking baseline Linux development tools"
$missingLinuxTools = @()
foreach ($tool in @("git", "curl", "tar")) {
    & wsl.exe -d $Distro -- sh -lc "command -v $tool >/dev/null 2>&1"
    if ($LASTEXITCODE -ne 0) { $missingLinuxTools += $tool }
}
if ($missingLinuxTools.Count -gt 0) {
    if (-not $InstallMissing) {
        throw "Missing WSL tools: $($missingLinuxTools -join ', '). Re-run with -InstallMissing."
    }
    Invoke-Wsl -Arguments @("sudo", "apt-get", "update") | Out-Null
    Invoke-Wsl -Arguments @("sudo", "apt-get", "install", "-y", "git", "curl", "ca-certificates", "tar", "build-essential") | Out-Null
}

# Use Linux line endings for new checkouts unless the Builder already chose another global policy.
$wslAutocrlf = (& wsl.exe -d $Distro -- git config --global --get core.autocrlf 2>$null | Out-String).Trim()
if (-not $wslAutocrlf) {
    Invoke-Wsl -Arguments @("git", "config", "--global", "core.autocrlf", "input") | Out-Null
}

# Carry Git identity into WSL only when WSL does not already have one.
if (Test-Command "git") {
    foreach ($key in @("user.name", "user.email")) {
        $existing = (& wsl.exe -d $Distro -- git config --global --get $key 2>$null | Out-String).Trim()
        if (-not $existing) {
            $hostValue = (& git config --global --get $key 2>$null | Out-String).Trim()
            if ($hostValue) { Invoke-Wsl -Arguments @("git", "config", "--global", $key, $hostValue) | Out-Null }
        }
    }
}

Write-Step "Checking VS Code WSL integration"
if (Test-Command "code") {
    & code --install-extension ms-vscode-remote.remote-wsl --force | Out-Null
} else {
    Write-Warning "VS Code 'code' command was not found on Windows. Install VS Code if you want the recommended Windows UI + WSL workspace flow."
}

Write-Step "Checking Docker Desktop / WSL integration"
if (-not $SkipDockerCheck) {
    $dockerDesktop = Get-Command "docker" -ErrorAction SilentlyContinue
    if (-not $dockerDesktop -and $InstallMissing -and (Test-Command "winget")) {
        & winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
        Write-Warning "Docker Desktop installation was requested. Start Docker Desktop, enable WSL integration for '$Distro', then rerun this command to verify Docker from WSL."
    }

    & wsl.exe -d $Distro -- docker info 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Docker is not operational inside '$Distro'. Start Docker Desktop and enable Settings > Resources > WSL Integration for '$Distro'. Do not install a second Docker Engine inside WSL just to satisfy this check."
    } else {
        Write-Host "Docker from WSL: PASS"
    }
}

if (-not $MigrateRepositories) {
    Write-Host ""
    Write-Host "WSL2 baseline setup: PASS"
    Write-Host "No repositories were migrated. Re-run with -MigrateRepositories -SourceRoot <windows-folder> when ready."
    exit 0
}

if (-not (Test-Command "git")) {
    throw "Windows Git is required for migration preflight so source repositories can be verified before copying state."
}

$destinationRootLinux = Resolve-WslDestinationRoot
Invoke-Wsl -Arguments @("mkdir", "-p", $destinationRootLinux) | Out-Null
$repositories = @(Get-RepositoryCandidates $SourceRoot)
if ($repositories.Count -eq 0) {
    throw "No Git repositories found at '$SourceRoot'."
}

Write-Step "Migrating $($repositories.Count) repository/repositories to ${Distro}:$destinationRootLinux"
$migrated = New-Object System.Collections.Generic.List[string]
$skipped = New-Object System.Collections.Generic.List[string]

foreach ($repo in $repositories) {
    $name = Split-Path $repo -Leaf
    $dirty = (& git -C $repo status --porcelain=v1 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Skipping '$repo': Git status failed."
        $skipped.Add($repo)
        continue
    }
    if ($dirty) {
        Write-Warning "Skipping '$repo': working tree is not clean. Commit/stash/reconcile it first so migration cannot lose local work."
        $skipped.Add($repo)
        continue
    }

    $head = Get-GitValue $repo @("rev-parse", "HEAD")
    $branch = Get-GitValue $repo @("branch", "--show-current")
    $origin = Get-GitValue $repo @("config", "--get", "remote.origin.url")
    $sourceLinux = Convert-ToWslPath $repo
    $destinationLinux = "$destinationRootLinux/$name"

    & wsl.exe -d $Distro -- test -e $destinationLinux
    if ($LASTEXITCODE -eq 0) {
        Write-Warning "Skipping '$repo': destination '$destinationLinux' already exists."
        $skipped.Add($repo)
        continue
    }

    if (-not $PSCmdlet.ShouldProcess($repo, "Create validated WSL2 checkout at $destinationLinux")) {
        continue
    }

    # Clone from the local clean repository so committed local-only refs remain available during migration.
    Invoke-Wsl -Arguments @("git", "clone", "--no-hardlinks", $sourceLinux, $destinationLinux) | Out-Null
    if ($origin) {
        Invoke-Wsl -Arguments @("git", "-C", $destinationLinux, "remote", "set-url", "origin", $origin) | Out-Null
    }

    $destHead = ((Invoke-Wsl -Arguments @("git", "-C", $destinationLinux, "rev-parse", "HEAD")) -join "`n").Trim()
    $destDirty = ((Invoke-Wsl -Arguments @("git", "-C", $destinationLinux, "status", "--porcelain=v1")) -join "`n").Trim()
    if ($destHead -ne $head) {
        throw "Migration verification failed for '$name': source HEAD $head != destination HEAD $destHead. Windows source was left untouched."
    }
    if ($destDirty) {
        throw "Migration verification failed for '$name': destination checkout is not clean. Windows source was left untouched."
    }

    if ($branch) {
        $destBranch = ((Invoke-Wsl -Arguments @("git", "-C", $destinationLinux, "branch", "--show-current")) -join "`n").Trim()
        if ($destBranch -ne $branch) {
            Write-Warning "'$name' migrated at the correct HEAD, but checked-out branch differs (source '$branch', destination '$destBranch')."
        }
    }

    Write-Host "Migrated: $repo -> ${Distro}:$destinationLinux"
    $migrated.Add($destinationLinux)
}

Write-Host ""
Write-Host "Migration complete."
Write-Host "Migrated: $($migrated.Count)"
Write-Host "Skipped:  $($skipped.Count)"
Write-Host "Windows source checkouts were NOT deleted."
Write-Host ""
Write-Host "Next: open a migrated repository from WSL and run its normal Project Forge/project readiness checks."
if ($migrated.Count -gt 0) {
    Write-Host "Example:"
    Write-Host "  wsl -d $Distro"
    Write-Host "  cd $($migrated[0])"
    Write-Host "  code ."
}
