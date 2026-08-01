param(
    [string]$PythonPath = "D:\Codex\venvs\medical-knowledge-hub\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$Port = 5000
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path -LiteralPath $EnvFile) {
    $PortLine = Get-Content -LiteralPath $EnvFile -Encoding UTF8 |
        Where-Object { $_ -match '^PORT=\d+$' } |
        Select-Object -Last 1
    if ($PortLine) { $Port = [int]($PortLine -replace '^PORT=', '') }
}
$BaseUrl = "http://127.0.0.1:$Port"
$HealthUrl = "$BaseUrl/api/health"
$AppUrl = "$BaseUrl/admin.html"
$LogRoot = "D:\Codex\state\medical-knowledge-hub\logs"

function Test-ContentHubHealth {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        return $Response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-ContentHubHealth)) {
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "Medical Knowledge Hub failed to start: Python was not found at $PythonPath. Run install.ps1 again.",
            "Medical Knowledge Hub"
        ) | Out-Null
        exit 1
    }
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    $Stdout = Join-Path $LogRoot "server.out.log"
    $Stderr = Join-Path $LogRoot "server.err.log"
    Start-Process -FilePath $PythonPath `
        -ArgumentList "app.py" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $Stdout `
        -RedirectStandardError $Stderr | Out-Null
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        if (Test-ContentHubHealth) { break }
        Start-Sleep -Milliseconds 500
    }
}

if (-not (Test-ContentHubHealth)) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "Medical Knowledge Hub failed to start. See $LogRoot for details.",
        "Medical Knowledge Hub"
    ) | Out-Null
    exit 1
}

Start-Process $AppUrl
