# Поднимает сайт (8002), бота + mini app (8001) и туннель ngrok. Уже запущенное не трогает.
# Ставится в автозапуск Windows задачей «CyberBounty autostart» (см. tools/install_autostart.ps1).
$site = "D:\проекты\сайты\pcclub-site"
$bot  = "D:\проекты\боты\cyberbounty-bot"
$ngrok = "C:\Users\tsar7\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
$domain = "surfboard-register-glimmer.ngrok-free.dev"

function Test-Port($p) { [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) }
function Start-Hidden($exe, $argList, $dir, $log) {
    Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $dir -WindowStyle Hidden `
        -RedirectStandardOutput "$log.out.log" -RedirectStandardError "$log.err.log"
}

# Следим раз в 30 с: упал сайт, бот или туннель — поднимаем снова. Работает без Claude и без чьих-либо сессий.
while ($true) {
    if (-not (Test-Port 8002)) { Start-Hidden "$site\.venv\Scripts\python.exe" "main.py" $site "$site\data\server" }
    if (-not (Test-Port 8001)) { Start-Hidden "$bot\.venv\Scripts\python.exe" "main.py" $bot "$bot\data\server" }
    Start-Sleep -Seconds 5
    if (-not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
        Start-Hidden $ngrok "http --url=$domain 8001" $site "$site\data\ngrok"
    }
    Start-Sleep -Seconds 30
}
