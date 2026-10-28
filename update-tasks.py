#!/usr/bin/env python3
"""按 config.json 的 term_schedule / exam_dates 重建 Windows 计划任务。

每个有课的日期注册一个一次性触发器，触发时间 = 第一节课前 30 分钟。
课表更新后重新运行：python update-tasks.py
"""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import briefing

ROOT = Path(__file__).resolve().parent
TASK_NAME = "早知道每日简报"


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    config, _ = briefing.load_config()
    term = config.get("term_schedule") or {}
    now = datetime.now()

    triggers = []
    for date_str, class_time in sorted(term.items()):
        try:
            class_dt = datetime.strptime(f"{date_str} {class_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"⚠ 跳过无法解析的课表项：{date_str} {class_time}")
            continue
        push_dt = class_dt - timedelta(minutes=30)
        if push_dt >= now - timedelta(minutes=1):  # 过去的触发不注册
            triggers.append(push_dt)

    if not triggers:
        print("config.json 里没有未来课程（term_schedule 为空或全部已过）。")
        print("每天固定时间推送：powershell -ExecutionPolicy Bypass -File install-task.ps1")
        return

    python = Path(sys.executable)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$action = New-ScheduledTaskAction -Execute '{python}' -Argument 'briefing.py' -WorkingDirectory '{ROOT}'",
        "$triggers = @()",
    ]
    for push_dt in triggers:
        args = f"{push_dt.year},{push_dt.month},{push_dt.day},{push_dt.hour},{push_dt.minute},0"
        lines.append(
            f"$triggers += New-ScheduledTaskTrigger -Once -At ([datetime]::new({args}))"
        )
    lines += [
        "$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable "
        "-ExecutionTimeLimit (New-TimeSpan -Minutes 10)",
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $triggers "
        "-Settings $settings -Description '每天第一节课前30分钟推送天气+通勤简报' -Force | Out-Null",
        "Write-Host '✅ 计划任务已更新，触发时间：'",
        "$triggers | ForEach-Object { Write-Host '  ' $_.StartBoundary }",
    ]

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "\n".join(lines)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
