# Один раз: создаёт задачу Windows, которая при входе в систему запускает tools\start_all.ps1.
# Удалить: Unregister-ScheduledTask -TaskName "CyberBounty autostart" -Confirm:$false
$script = "D:\проекты\сайты\pcclub-site\tools\start_all.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "CyberBounty autostart" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
"Готово: задача «CyberBounty autostart» создана."
