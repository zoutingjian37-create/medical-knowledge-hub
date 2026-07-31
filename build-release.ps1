param(
    [string]$OutputRoot = "D:\Codex\releases\medical-knowledge-hub"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$ResolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)
$PackageDir = Join-Path $ResolvedOutput "medical-knowledge-hub-windows"
$ZipPath = Join-Path $ResolvedOutput "medical-knowledge-hub-windows.zip"

New-Item -ItemType Directory -Path $ResolvedOutput -Force | Out-Null
$OutputPrefix = $ResolvedOutput.TrimEnd('\') + '\'
$ResolvedPackage = [System.IO.Path]::GetFullPath($PackageDir)
if (-not $ResolvedPackage.StartsWith($OutputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Release package path escaped the selected output directory."
}
if (Test-Path -LiteralPath $ResolvedPackage) {
    Remove-Item -LiteralPath $ResolvedPackage -Recurse -Force
}
New-Item -ItemType Directory -Path $ResolvedPackage -Force | Out-Null

$Manifest = & python (Join-Path $ProjectRoot "release_manifest.py") --root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Unable to build the release manifest."
}
foreach ($Relative in $Manifest) {
    $Source = Join-Path $ProjectRoot $Relative
    $Destination = Join-Path $ResolvedPackage $Relative
    $DestinationParent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $DestinationParent -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $ResolvedPackage "*") -DestinationPath $ZipPath -Force

Write-Output "package=$ResolvedPackage"
Write-Output "zip=$ZipPath"
