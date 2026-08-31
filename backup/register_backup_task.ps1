<#
    Registers a Windows Scheduled Task that runs backup_bedtracker.py
    every Sunday, repeating through the day, resuming after missed starts,
    and only when a network connection is available.

    Run this ONCE, from an ordinary (non-admin) PowerShell:

        powershell -ExecutionPolicy Bypass -File .\register_backup_task.ps1

    Re-run it any time to update the schedule. Remove it with:

        Unregister-ScheduledTask -TaskName "BedTracker Weekly Backup" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$TaskName   = "BedTracker Weekly Backup"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackupPy   = Join-Path $ScriptDir "backup_bedtracker.py"
$ProjectDir = Split-Path -Parent $ScriptDir

# Prefer the project's virtual-env Python; fall back to whatever "python" is.
$Venv = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $Venv) { $Python = $Venv }
else {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $Python) { throw "Could not find python. Install Python or create the .venv." }
}

Write-Host "Python : $Python"
Write-Host "Script : $BackupPy"

if (-not (Test-Path (Join-Path $ScriptDir "backup.env"))) {
    Write-Warning "backup.env not found - copy backup.env.example to backup.env first."
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$BackupPy`"" -WorkingDirectory $ScriptDir

# Weekly on Sunday at 08:00, then repeat every 2 hours for 12 hours.
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 8:00AM
$Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 8:00AM `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration (New-TimeSpan -Hours 12)).Repetition

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Run as the current user, only when signed in (no stored password, $0).
$Principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal -Force `
    -Description "Automatic BedTracker database backups (Anki-style)." | Out-Null

Write-Host ""
Write-Host "Registered '$TaskName'." -ForegroundColor Green
Write-Host "Test it now with:  Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host "Then check:        python `"$BackupPy`" --status"
