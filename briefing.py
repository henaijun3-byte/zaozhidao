#!/usr/bin/env python3
"""早知道 · 每日简报：天气 + 通勤路线 + 微信推送（新加坡版）。

数据源（全部免费、无需 key）
  天气     Open-Meteo
  地址解析  Nominatim（OpenStreetMap）
  路线     OSRM（OpenStreetMap 路由，按畅通估算）
  实时路况  点开 Google Maps 深链查看
  叫车     Grab 深链（手机上直接打开 Grab 叫车）
  推送     Server酱 → 微信

用法
  python briefing.py               # 生成今日简报并推送到微信（计划任务每天调用）
  python briefing.py --json        # 只生成简报并打印 JSON（调试）
  python briefing.py --no-push     # 生成简报并打印 Markdown，不推送
  python briefing.py --config 路径  # 使用指定配置文件
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.json"

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
OSRM_ROUTES = (
    "https://router.project-osrm.org/route/v1/driving",
    "https://routing.openstreetmap.de/routed-car/route/v1/driving",
)
WEATHER_API = "https://api.open-meteo.com/v1/forecast"
SERVERCHAN_API = "https://sctapi.ftqq.com/{key}.send"

DEFAULT_SETTINGS = {
    "origin": "",            # 家（文本地址）
    "destination": "",       # 学校
    "city": "",              # 所在城市，帮助地理编码
    "timezone": "Asia/Singapore",
    "arrival_time": "",      # 到校时间 HH:MM（没有课表时用于倒推出门时间）
    "schedule": {},          # 按星期的第一节课，例如 {"mon": "09:00", "tue": "10:00"}
    "term_schedule": {},     # 按日期的第一节课（课表解析结果），例如 {"2026-10-14": "12:00"}
    "exam_dates": [],        # 考试日期，例如 ["2026-11-24"]
    "push_time": "07:00",    # 计划任务兜底推送时间
    "serverchan_sendkey": "",
    "home_coord": None,      # 家坐标 "lng,lat"，首次地理编码后自动缓存
    "school_coord": None,
}

HTTP_HEADERS = {"User-Agent": "zaozhidao/0.2 (personal morning assistant)"}
TIMEOUT = 20


def load_config(path=DEFAULT_CONFIG):
    """读取配置，缺失字段用默认值补齐；返回 (config, path)。

    文件损坏（例如手工编辑时写错）时不崩溃，退回默认值并提示。
    """
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("配置内容不是 JSON 对象")
        except (json.JSONDecodeError, ValueError, OSError) as error:
            print(f"⚠ 配置文件 {path.name} 读取出错（{error}），已按默认值继续。", file=sys.stderr)
            data = {}
    return {**DEFAULT_SETTINGS, **data}, path


def save_config(config, path):
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def weather_info(code):
    """Open-Meteo WMO 天气代码 → (描述, 符号, 出门建议)。"""
    if code == 0:
        return "晴", "☀", "适合出门"
    if code in (1, 2):
        return "晴间多云", "⛅", "带件外套"
    if code == 3:
        return "阴", "☁", "注意保暖"
    if code in (45, 48):
        return "有雾", "〰", "出行注意安全"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "有雨", "☂", "建议带伞"
    if code in (71, 73, 75, 77, 85, 86):
        return "有雪", "❄", "注意路面湿滑"
    if code in (95, 96, 99):
        return "有雷雨", "⛈", "留意天气变化"
    return "天气已更新", "☼", "出门注意安全"


def fetch_weather(lat, lon, timezone="Asia/Singapore"):
    """Open-Meteo 实况 + 当日预报（免 key）。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": timezone,
        "forecast_days": 1,
    }
    resp = httpx.get(WEATHER_API, params=params, headers=HTTP_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    current, daily = data.get("current"), data.get("daily")
    if not current or not daily:
        raise RuntimeError("天气服务暂时没有返回完整数据")
    condition, symbol, advice = weather_info(current.get("weather_code"))
    return {
        "condition": condition,
        "symbol": symbol,
        "advice": advice,
        "temp": round(current.get("temperature_2m") or 0),
        "temp_min": round((daily.get("temperature_2m_min") or [0])[0]),
        "temp_max": round((daily.get("temperature_2m_max") or [0])[0]),
        "rain_prob": (daily.get("precipitation_probability_max") or [None])[0],
        "wind_kmh": round(current.get("wind_speed_10m") or 0),
    }


def geocode(config, cfg_path, address, which):
    """Nominatim 地理编码，坐标缓存回 config（"lng,lat" 格式）。

    地址常写成「路名, 小区名 邮编」，逗号会干扰 Nominatim 解析；
    完整查询失败时去掉逗号后的部分重试。
    """
    city = config["city"]
    candidates = [f"{address}, {city}" if city else address]
    if "," in address:
        head = address.split(",")[0]
        candidates.append(f"{head}, {city}" if city else head)
    for query in candidates:
        time.sleep(1.1)  # Nominatim 使用条款要求最多 1 次/秒
        resp = httpx.get(
            NOMINATIM_SEARCH,
            params={"q": query, "format": "json", "limit": 1},
            headers=HTTP_HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat, lon = results[0]["lat"], results[0]["lon"]
            coord = f"{lon},{lat}"
            config[f"{which}_coord"] = coord
            save_config(config, cfg_path)
            return coord
    raise RuntimeError(f"地址没找到：{address}（建议写得更具体，带上路名或区名）")


def resolve_coords(config, cfg_path):
    """取家/学校坐标，缺失时自动地理编码。返回 (home, school)。"""
    home, school = config["home_coord"], config["school_coord"]
    if not home and config["origin"]:
        home = geocode(config, cfg_path, config["origin"], "home")
    if not school and config["destination"]:
        school = geocode(config, cfg_path, config["destination"], "school")
    return home, school


def fetch_commute(home, school, target_time=""):
    """OSRM 驾车路线（按畅通估算时长）。target_time 为第一节课/到校时间。"""
    if not (home and school):
        raise RuntimeError("缺少家或学校的坐标（地理编码失败）")
    last_error = None
    for base in OSRM_ROUTES:
        try:
            resp = httpx.get(
                f"{base}/{home};{school}?overview=false",
                headers=HTTP_HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                raise RuntimeError(f"路线服务返回 {data.get('code', '无路线')}")
            route = data["routes"][0]
            commute = {
                "duration_min": max(1, round(route["duration"] / 60)),
                "distance_km": round(route["distance"] / 1000, 1),
                "congestion": "畅通估算（实时路况见 Google Maps）",
                "congestion_desc": "",
            }
            if target_time:
                try:
                    target = datetime.strptime(target_time, "%H:%M")
                    leave = target - timedelta(minutes=commute["duration_min"] + 10)
                    commute["leave_time"] = leave.strftime("%H:%M")
                    commute["target_time"] = target_time
                except ValueError:
                    pass
            return commute
        except Exception as error:
            last_error = error
    raise RuntimeError(f"路线计算失败：{last_error}")


def build_links(config, home, school):
    """Google Maps 路线深链 + Grab 叫车深链（手机点开即进 App）。"""
    params = {}
    if config["origin"]:
        params["origin"] = config["origin"]
    if config["destination"]:
        params["destination"] = config["destination"]
    params["travelmode"] = "driving"
    map_url = f"https://www.google.com/maps/dir/?api=1&{urlencode(params)}"
    taxi_url = map_url  # 坐标没解析出来时退回 Google Maps
    if home and school:
        lon_home, lat_home = (value.strip() for value in home.split(","))
        lon_school, lat_school = (value.strip() for value in school.split(","))
        grab = {
            "screenType": "BOOK",
            "pickupLatitude": lat_home,
            "pickupLongitude": lon_home,
            "dropoffLatitude": lat_school,
            "dropoffLongitude": lon_school,
        }
        if config["origin"]:
            grab["pickupAddress"] = config["origin"]
        if config["destination"]:
            grab["dropoffAddress"] = config["destination"]
        taxi_url = f"grab://open?{urlencode(grab)}"
    return {"map_url": map_url, "taxi_url": taxi_url}


def build_signals(briefing):
    """网页端「今日情报」卡片。"""
    signals = []
    weather = briefing["weather"]
    if weather:
        signals.append(
            {
                "category": "weather",
                "label": "天气提醒",
                "time": briefing["generated_at"],
                "title": f"{weather['condition']}，{weather['temp_min']}~{weather['temp_max']}°",
                "body": f"{weather['advice']}；降水概率 {weather['rain_prob']}%，风速 {weather['wind_kmh']} km/h。",
                "url": None,
                "source": f"{weather['location']} · Open-Meteo",
            }
        )
    commute = briefing["commute"]
    if commute:
        leave_text = (
            f"，建议 {commute['leave_time']} 前出门" if commute.get("leave_time") else ""
        )
        signals.append(
            {
                "category": "commute",
                "label": "出行提醒",
                "time": briefing["generated_at"],
                "title": f"通勤约 {commute['duration_min']} 分钟",
                "body": f"{commute['distance_km']} km{leave_text}。畅通估算，出门前点开地图看实时路况。",
                "url": briefing["map_url"],
                "source": "OSRM 路线 · 实时路况看 Google Maps",
            }
        )
    signals.append(
        {
            "category": "daily",
            "label": "叫车直达",
            "time": briefing["generated_at"],
            "title": "一键叫车上学",
            "body": "出发地和目的地已填好，打开 Grab 确认路线、价格后下单。",
            "url": briefing["taxi_url"],
            "source": "Grab",
        }
    )
    return signals


def build_briefing(config, cfg_path=DEFAULT_CONFIG):
    """生成今日简报。任何数据源失败都不会中断，只记入 notes。"""
    now = datetime.now()
    briefing = {
        "date": f"{now.month}月{now.day}日",
        "weekday": "星期" + "一二三四五六日"[now.weekday()],
        "generated_at": now.strftime("%H:%M"),
        "weather": None,
        "commute": None,
        "signals": [],
        "summary": "",
        "notes": [],
    }
    notes = []

    # 课表：优先按日期查 term_schedule，其次按星期查 schedule，最后用固定到校时间
    today_key = now.strftime("%Y-%m-%d")
    term_class = (config.get("term_schedule") or {}).get(today_key, "")
    weekday_key = now.strftime("%a").lower()  # mon/tue/wed/...
    weekday_class = (config.get("schedule") or {}).get(weekday_key, "")
    first_class = term_class or weekday_class
    target_time = first_class or config["arrival_time"]
    if first_class:
        briefing["first_class"] = first_class
        briefing["is_exam"] = today_key in (config.get("exam_dates") or [])

    try:
        home, school = resolve_coords(config, cfg_path)
    except Exception as error:
        home, school = None, None
        notes.append(f"地址解析失败：{error}")
    briefing.update(build_links(config, home, school))

    if home:
        try:
            lon, lat = (float(value) for value in home.split(","))  # 坐标是 "lng,lat"
            weather = fetch_weather(lat, lon, config.get("timezone", "Asia/Singapore"))
            weather["location"] = config["city"] or "家附近"
            briefing["weather"] = weather
        except Exception as error:
            notes.append(f"天气获取失败：{error}")
    else:
        notes.append("家地址还没解析成功，天气无法定位")

    if home and school:
        try:
            briefing["commute"] = fetch_commute(home, school, target_time)
        except Exception as error:
            notes.append(f"路线获取失败：{error}")
    else:
        notes.append("家或学校地址还没解析成功，暂无通勤路线")

    parts = []
    weather = briefing["weather"]
    if weather:
        rain = "无降水" if weather["rain_prob"] == 0 else f"降水概率 {weather['rain_prob']}%"
        parts.append(f"今天{weather['condition']}，{weather['temp_min']}~{weather['temp_max']}°C，{rain}")
    if first_class:
        label = "有考试" if briefing.get("is_exam") else "第一节课"
        parts.append(f"今天{label} {first_class}")
    commute = briefing["commute"]
    if commute:
        parts.append(f"通勤约 {commute['duration_min']} 分钟")
        if commute.get("leave_time"):
            target_label = f"（{first_class} 上课）" if first_class else ""
            parts.append(f"建议 {commute['leave_time']} 前出门{target_label}")
    if notes:
        parts.append("提示：" + "；".join(notes))
    briefing["summary"] = (
        ("。".join(parts) + "。") if parts else "还没配置好地址，先在「我的通勤设置」里填写吧。"
    )
    briefing["notes"] = notes
    briefing["signals"] = build_signals(briefing)
    return briefing


def render_markdown(briefing):
    """把简报渲染成微信推送用的 Markdown。"""
    sections = []
    weather = briefing["weather"]
    if weather:
        sections.append("## 🌤 天气")
        sections.append(
            f"{weather['condition']}，{weather['temp_min']}~{weather['temp_max']}°C，"
            f"降水概率 {weather['rain_prob']}%，风速 {weather['wind_kmh']} km/h"
        )
        sections.append(f"出门建议：{weather['advice']}")
    if briefing.get("first_class"):
        if briefing.get("is_exam"):
            sections.append("## 📝 今天有考试")
            sections.append(f"{briefing['first_class']} 开始，加油！")
        else:
            sections.append("## 📚 今天第一节课")
            sections.append(f"{briefing['first_class']} 开始")
    commute = briefing["commute"]
    if commute:
        sections.append("## 🚗 通勤")
        sections.append(
            f"{commute['distance_km']} km · 畅通约 {commute['duration_min']} 分钟 · 实时路况点开地图看"
        )
        if commute.get("leave_time"):
            sections.append(f"建议 {commute['leave_time']} 前出门（第一节课 {commute['target_time']}）")
    sections.append("## 🚕 一键叫车")
    sections.append(f"[打开 Grab 叫车]({briefing['taxi_url']}) ｜ [Google Maps 路线]({briefing['map_url']})")
    if briefing["notes"]:
        sections.append("## ⚠ 待完善")
        sections.extend(f"- {note}" for note in briefing["notes"])
    return "\n\n".join(sections)


def push_serverchan(sendkey, title, desp):
    """Server酱 v2 推送，返回推送数据。"""
    resp = httpx.post(
        SERVERCHAN_API.format(key=sendkey),
        data={"title": title, "desp": desp},
        headers=HTTP_HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Server酱推送失败：{data.get('message', data)}")
    return data


def main():
    # Windows 控制台默认 GBK，统一输出 UTF-8 避免中文乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="早知道 · 每日简报")
    parser.add_argument("--json", action="store_true", help="只打印 JSON，不推送")
    parser.add_argument("--no-push", action="store_true", help="打印 Markdown，不推送")
    parser.add_argument("--force", action="store_true", help="跳过推送时间检查，立即推送")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="配置文件路径")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    config, _ = load_config(cfg_path)

    # 推送时间门控：有课的日子只在第一节课前 30 分钟推送（计划任务按此注册）
    if not (args.json or args.no_push or args.force):
        now = datetime.now()
        today_key = now.strftime("%Y-%m-%d")
        first_class = (config.get("term_schedule") or {}).get(today_key, "") or (
            (config.get("schedule") or {}).get(now.strftime("%a").lower(), "")
        )
        if not first_class:
            print("今天课表里没有课，不推送。用 --force 强制推送，或 --no-push 只看简报。")
            return
        class_time = datetime.strptime(first_class, "%H:%M").time()
        class_dt = datetime.combine(now.date(), class_time)
        push_dt = class_dt - timedelta(minutes=30)
        if now < push_dt:
            print(
                f"还没到推送时间（第一节课 {first_class}，前 30 分钟 = {push_dt.strftime('%H:%M')}），"
                "到点由计划任务运行。"
            )
            return

    briefing = build_briefing(config, cfg_path)

    if args.json:
        print(json.dumps(briefing, ensure_ascii=False, indent=2))
        return
    markdown = render_markdown(briefing)
    print(markdown)
    if args.no_push:
        return
    sendkey = config["serverchan_sendkey"]
    if not sendkey:
        print("\n⚠ 未配置 serverchan_sendkey，跳过微信推送（见 config.json）。", file=sys.stderr)
        return
    if briefing.get("is_exam"):
        title = f"早知道 · {briefing['date']} {briefing['weekday']} · {briefing['first_class']} 考试"
    elif briefing.get("first_class"):
        title = f"早知道 · {briefing['date']} {briefing['weekday']} · 第一节课 {briefing['first_class']}"
    else:
        title = f"早知道 · {briefing['date']} {briefing['weekday']}简报"
    push_serverchan(sendkey, title, markdown)
    print("\n✅ 已推送到微信")


if __name__ == "__main__":
    main()
