param(
    [string]$RuntimeDir = "D:\Codex\tools\opencli-runtime",
    [string]$Version = "1.8.6"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

$userProfileDir = [Environment]::GetFolderPath("UserProfile")
$codexDependencies = Join-Path $userProfileDir ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$bundledPnpm = Join-Path $codexDependencies "bin\fallback\pnpm.cmd"
$bundledNode = Join-Path $codexDependencies "node\bin\node.exe"

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
$pnpmPath = if ($pnpm) { $pnpm.Source } elseif (Test-Path -LiteralPath $bundledPnpm) { $bundledPnpm } else { $null }

if ($pnpmPath) {
    $storeDir = "D:\Codex\cache\pnpm-store"
    & $pnpmPath add --dir $RuntimeDir "@jackwener/opencli@$Version" --store-dir $storeDir --ignore-scripts
} elseif ($npm) {
    $cacheDir = "D:\Codex\cache\npm"
    & $npm.Source install --prefix $RuntimeDir "@jackwener/opencli@$Version" --cache $cacheDir --ignore-scripts
} else {
    throw "npm or pnpm was not found. Install Node.js 20 or newer first."
}

$cli = Join-Path $RuntimeDir "node_modules\@jackwener\opencli\dist\src\main.js"
if (-not (Test-Path -LiteralPath $cli)) {
    throw "OpenCLI installation is incomplete: $cli was not found."
}

$node = Get-Command node -ErrorAction SilentlyContinue
$nodePath = if ($node) { $node.Source } elseif (Test-Path -LiteralPath $bundledNode) { $bundledNode } else { $null }
if (-not $nodePath) {
    throw "OpenCLI was downloaded, but Node.js was not found."
}

& $nodePath $cli --version
Write-Host "Platform collection engine installed at $RuntimeDir"
Write-Host "Next: install OpenCLI Browser Bridge, then check the connection on the Platforms page."
