param(
    [string]$InstallRoot = "D:\Codex\medical-knowledge-hub",
    [string]$VenvRoot = "D:\Codex\venvs\medical-knowledge-hub",
    [string]$VaultPath = "",
    [string]$CodexCli = "",
    [switch]$SkipWeChatDiscovery,
    [switch]$CreateDesktopShortcut
)

$ErrorActionPreference = "Stop"
$SourceRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$ResolvedInstall = [System.IO.Path]::GetFullPath($InstallRoot)
$ResolvedVenv = [System.IO.Path]::GetFullPath($VenvRoot)

New-Item -ItemType Directory -Path $ResolvedInstall -Force | Out-Null
if (-not $SourceRoot.Equals($ResolvedInstall, [System.StringComparison]::OrdinalIgnoreCase)) {
    $Manifest = & python (Join-Path $SourceRoot "release_manifest.py") --root $SourceRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the installation manifest."
    }
    foreach ($Relative in $Manifest) {
        $Source = Join-Path $SourceRoot $Relative
        $Destination = Join-Path $ResolvedInstall $Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $ResolvedVenv "Scripts\python.exe"))) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $ResolvedVenv) -Force | Out-Null
    python -m venv $ResolvedVenv
}
$AppPython = Join-Path $ResolvedVenv "Scripts\python.exe"
& $AppPython -m pip install --disable-pip-version-check -r (Join-Path $ResolvedInstall "requirements.txt")
if (-not $SkipWeChatDiscovery) {
    & $AppPython -m pip install --disable-pip-version-check -r (Join-Path $ResolvedInstall "requirements-wechat-ui.txt")
}

$CodexSkills = Join-Path $env:USERPROFILE ".codex\skills"
$InstalledSkills = @()
foreach ($SkillName in @("distill-medical-literature", "distill-medical-wechat")) {
    $SkillSource = Join-Path $ResolvedInstall (Join-Path "skills" $SkillName)
    $SkillDestination = Join-Path $CodexSkills $SkillName
    New-Item -ItemType Directory -Path $SkillDestination -Force | Out-Null
    Copy-Item -Path (Join-Path $SkillSource "*") -Destination $SkillDestination -Recurse -Force
    $InstalledSkills += $SkillDestination
}

$EnvPath = Join-Path $ResolvedInstall ".env"
$CreatedEnv = -not (Test-Path -LiteralPath $EnvPath)
if (-not (Test-Path -LiteralPath $EnvPath)) {
    Copy-Item -LiteralPath (Join-Path $ResolvedInstall "env.example") -Destination $EnvPath
}
$Lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8 | Where-Object { $_ -notmatch '^CONTENT_HUB_MANAGE_TASK_SCHEDULER=' }
$Lines += "CONTENT_HUB_MANAGE_TASK_SCHEDULER=1"
Set-Content -LiteralPath $EnvPath -Value $Lines -Encoding UTF8
if ($CreatedEnv) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ResolvedInstall "install-automation-task.ps1") -ProjectRoot $ResolvedInstall -PythonExe $AppPython -Disable
}
if ($VaultPath) {
    $Lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8 | Where-Object { $_ -notmatch '^OBSIDIAN_VAULT_PATH=' }
    $Lines += "OBSIDIAN_VAULT_PATH=$VaultPath"
    Set-Content -LiteralPath $EnvPath -Value $Lines -Encoding UTF8
}
$CodexCandidates = @(
    $CodexCli,
    "D:\Codex\codex-cli\codex.exe",
    (Get-Command codex -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$ResolvedCodexCli = $CodexCandidates | Select-Object -First 1
if ($ResolvedCodexCli) {
    $Lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8 | Where-Object { $_ -notmatch '^CONTENT_HUB_CODEX_CLI=' }
    $Lines += "CONTENT_HUB_CODEX_CLI=$ResolvedCodexCli"
    Set-Content -LiteralPath $EnvPath -Value $Lines -Encoding UTF8
}

if ($CreateDesktopShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "Medical Knowledge Hub.lnk"))
    $Launcher = Join-Path $ResolvedInstall "start.bat"
    $Icon = Join-Path $ResolvedInstall "assets\medical-knowledge-hub.ico"
    $Shortcut.TargetPath = $Launcher
    $Shortcut.IconLocation = $Icon
    $Shortcut.WorkingDirectory = $ResolvedInstall
    $Shortcut.Description = "医学知识提炼与 Obsidian 归档"
    $Shortcut.Save()
    $IconRefresh = Join-Path $env:SystemRoot "System32\ie4uinit.exe"
    if (Test-Path -LiteralPath $IconRefresh) {
        & $IconRefresh -show
    }
}

Push-Location $ResolvedInstall
try {
    & $AppPython -c "from app import app; assert app.title == 'Medical Knowledge Hub'"
} finally {
    Pop-Location
}

Write-Output "installed=$ResolvedInstall"
Write-Output "python=$AppPython"
Write-Output "skills=$($InstalledSkills -join ';')"
