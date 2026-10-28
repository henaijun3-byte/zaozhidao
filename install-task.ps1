# 注册/删除「早知道每日简报」Windows 计划任务。
# 用法：
#   powershell -ExecutionPolicy Bypass -File install-task.ps1           # 按 config.json 的 push_time 注册
#   powershell -ExecutionPolicy Bypass -File install-task.ps1 -Time 07:20
#   powershell -ExecutionPolicy Bypass -File install-task.ps1 -Remove   # 删除任务
param(
  [string]$Time = "",
  [switch]$Remove
)
$ErrorActionPreference = "Stop"
$TaskName = "早知道每日简报"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "已删除计划任务：$TaskName"
  exit 0
}

$Root = $PSScriptRoot
if (-not $Time) {
  $CfgPath = Join-Path $Root "config.json"
  if (Test-Path $CfgPath) {
    $Time = (Get-Content $CfgPath -Raw | ConvertFrom-Json).push_time
  }
  if (-not $Time) { $Time = "07:00" }
}

$Python = (Get-Command python).Source
$Action = New-ScheduledTaskAction -Execute $Python -Argument "briefing.py" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
  -Description "每天早上抓取天气与路况，生成简报推送到微信" -Force | Out-Null

Write-Host "已注册计划任务：$TaskName（每天 $Time 运行，支持唤醒电脑）"
Write-Host "修改时间：先改 config.json 的 push_time，再重新运行本脚本"
