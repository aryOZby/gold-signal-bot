# רישום Scheduled Task שמפעיל את הבוט בכל התחברות ומרים אותו מחדש אחרי קריסה.
# הרצה (PowerShell כמנהל):
#   powershell -ExecutionPolicy Bypass -File scripts\vps\install-task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\vps\install-task.ps1 -Target scripts\listen_only.py

param(
    [string]$Target = "main.py",
    [string]$TaskName = "GoldSignalBot"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunBat = Join-Path $Root "scripts\vps\run.bat"
if (-not (Test-Path $RunBat)) { throw "Missing $RunBat" }

# run.bat כבר מכיל לולאת restart, לכן המשימה עצמה לא אמורה להסתיים לעולם.
# cmd דורש את הצורה:  /c ""<נתיב עם רווחים>" <ארגומנט>"
$Argument = '/c ""' + $RunBat + '" ' + $Target + '"'
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $Argument -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger -AtLogOn

# ExecutionTimeLimit=0 מבטל את מגבלת 3 הימים שמחסלת משימות ארוכות.
$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

# Interactive = רץ בתוך ה-session של המשתמש, אחרת הוא לא יראה את MT5.
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host ""
Write-Host "Scheduled task '$TaskName' installed and started." -ForegroundColor Green
Write-Host "  target : $Target"
Write-Host "  folder : $Root"
Write-Host ""
Write-Host "פקודות שימושיות:"
Write-Host "  Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo"
Write-Host "  Stop-ScheduledTask -TaskName $TaskName"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host ""
Write-Host "חשוב: התנתק מה-RDP ב-Disconnect ולא ב-Sign out, אחרת ה-session נסגר" -ForegroundColor Yellow
Write-Host "      והבוט (וגם MT5) ייעצרו." -ForegroundColor Yellow
