#!/usr/bin/env python3
"""早知道 · 新手配置向导。

跟着提示一步步填写，自动生成 config.json、验证高德 key 和地址，
最后生成一份真实简报预览，可选测试推送到微信。
用法：python setup.py
"""

import sys
from pathlib import Path

import briefing

ROOT = Path(__file__).resolve().parent


def ask(prompt, default=""):
    suffix = f"（直接回车使用默认 {default}）" if default else ""
    answer = input(f"{prompt}{suffix}\n> ").strip()
    return answer or default


def ask_yes(prompt):
    return input(f"{prompt}（y/n）\n> ").strip().lower().startswith("y")


def collect_inputs(config):
    print("\n" + "=" * 46)
    print("早知道 · 配置向导（填一次，之后不用再动）")
    print("=" * 46)
    config["serverchan_sendkey"] = ask("1/6 微信推送 SendKey（暂时没有可回车跳过）", config["serverchan_sendkey"])
    if not config["serverchan_sendkey"]:
        print("   → 之后想要微信推送：浏览器打开 https://sct.ftqq.com 用微信扫码，\n     复制 SendKey 后再跑一次本向导。")
    config["city"] = ask("2/6 你所在的城市（例如：Singapore）", config["city"])
    config["origin"] = ask("3/6 你的家庭住址（越具体越准，例如：123 Orchard Rd 238858）", config["origin"])
    config["destination"] = ask("4/6 你的学校名称或地址（例如：National University of Singapore）", config["destination"])
    config["arrival_time"] = ask("5/6 每天几点到校（HH:MM，有课表后此项被忽略）", config["arrival_time"] or "08:00")
    config["push_time"] = ask("6/6 每天早上几点推送简报（HH:MM）", config["push_time"] or "07:00")
    print("   → 课表写在 config.json 的 term_schedule 字段里（日期 → 第一节课时间），\n     然后运行 python update-tasks.py 注册计划任务：每节课前 30 分钟自动推送。")
    return config


def validate(config, cfg_path):
    print("\n正在验证地址…")
    errors = []
    home = school = None
    if config["origin"]:
        try:
            home = briefing.geocode(config, cfg_path, config["origin"], "home")
            print(f"✅ 家地址解析成功：{home}")
        except Exception as error:
            errors.append(("家地址", str(error)))
    else:
        print("⚠ 家地址留空了，跳过验证（可以之后重新运行本向导补上）。")
    if config["destination"]:
        try:
            school = briefing.geocode(config, cfg_path, config["destination"], "school")
            print(f"✅ 学校地址解析成功：{school}")
        except Exception as error:
            errors.append(("学校地址", str(error)))
    else:
        print("⚠ 学校地址留空了，跳过验证（可以之后重新运行本向导补上）。")
    if not errors:
        try:
            commute = briefing.fetch_commute(home, school, config["arrival_time"])
            print(f"✅ 路线获取成功：{commute['distance_km']} km，约 {commute['duration_min']} 分钟（畅通估算）")
        except Exception as error:
            print(f"⚠ 路线获取失败（不影响天气）：{error}")
    for label, error in errors:
        print(f"❌ {label}解析失败：{error}")
        print("   → OpenStreetMap 没识别出这个地址，建议写得更具体\n     （带上路名、邮编或区名），或换成附近的地标建筑。")
    if errors:
        print("\n请检查后重新运行 python setup.py（已填的内容会保留）。")
        return False
    return True


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    cfg_path = briefing.DEFAULT_CONFIG
    config, _ = briefing.load_config(cfg_path)
    config = collect_inputs(config)
    briefing.save_config(config, cfg_path)
    print(f"\n已保存到 {cfg_path.name}")

    if not validate(config, cfg_path):
        return

    current = briefing.build_briefing(config, cfg_path)
    print("\n今日简报预览：")
    print("-" * 46)
    print(briefing.render_markdown(current))

    if config["serverchan_sendkey"] and ask_yes("\n是否现在测试推送一条到你的微信？"):
        try:
            briefing.push_serverchan(
                config["serverchan_sendkey"],
                f"早知道 · 测试推送 {current['date']}",
                briefing.render_markdown(current),
            )
            print("✅ 已发送，去微信看看收到没有。")
        except Exception as error:
            print(f"❌ 推送失败：{error}")

    print("\n全部完成！每天早上由 Windows 计划任务自动推送。")
    print("网页版：运行 python server.py 后打开 http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
