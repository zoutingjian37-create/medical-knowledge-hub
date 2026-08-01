param(
    [string]$ProjectRoot = "D:\Codex\medical-knowledge-hub",
    [string]$PythonExe = "D:\Codex\venvs\medical-knowledge-hub\Scripts\python.exe",
    [ValidatePattern('^\d{2}:\d{2}$')]
    [string]$RunTime = "08:30",
    [switch]$Disable
)

$ErrorActionPreference = "Stop"
$taskName = "Medical Knowledge Hub Daily"

if ($Disable) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
    }
    return
}

$arguments = "-m extensions.subscriptions.worker"
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $RunTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null
