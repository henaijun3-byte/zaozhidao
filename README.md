# 早知道 · 每日通勤助手（新加坡版）

每天早上，把天气、上学路况浓缩成一条微信推送：出门前 60 秒看完，一键跳转 Grab 叫车。

- 前端：PWA（`index.html` / `app.js`，可离线打开）
- 后端：Python（`briefing.py` 抓数据+推送，`server.py` 起本地网页和 API）
- 数据源（全部免费、无需 key）：
  - 天气：Open-Meteo
  - 地址解析：Nominatim（OpenStreetMap）
  - 路线时长：OSRM（畅通估算；实时路况点开 Google Maps 深链）
  - 叫车：Grab 深链（手机上点开直接进 Grab 填好起点终点）
  - 推送：Server酱 → 微信（唯一需要注册的）

## 快速开始

1. **安装依赖**

   ```
   pip install -r requirements.txt
   ```

2. **注册 Server酱 SendKey（2 分钟）**

   https://sct.ftqq.com → 微信扫码登录 → 复制 SendKey

3. **运行配置向导（新手推荐）**

   ```
   python setup.py
   ```

   跟着提示粘贴 SendKey、填写城市和地址即可。向导会自动解析地址、
   拉取真实路线、预览今天的简报，并可选测试推送一条到微信。

   课表：编辑 `config.json` 的 `term_schedule` 字段（日期 → 第一节课时间），
   例如 `{"2026-10-14": "12:00", "2026-10-19": "15:30"}`；考试日期写进
   `exam_dates`。有课的当天，简报会在**第一节课前 30 分钟**推送，
   并按上课时间倒推建议出门时间。

4. **试跑一次**

   ```
   python briefing.py --no-push   # 只打印简报，不推送
   python briefing.py             # 直接推送到微信
   ```

5. **注册计划任务**

   ```
   python update-tasks.py
   ```

   读取 `term_schedule`，为每个有课的日期注册一个一次性触发
   （第一节课前 30 分钟），支持唤醒电脑。课表更新后重新运行即可。
   没有课表时可用 `install-task.ps1` 注册每天固定时间的任务。

6. **启动本地网页（可选，随时看）**

   ```
   python server.py
   ```

   浏览器打开 http://127.0.0.1:8000 ，刷新即抓取实时数据。

## 目录结构

| 文件 | 作用 |
| --- | --- |
| `setup.py` | 新手配置向导：一步步填写并自动验证地址 |
| `briefing.py` | 核心：抓天气/路线 → 生成简报 → 推送微信，可单独运行 |
| `server.py` | FastAPI 本地服务：网页 + `/api/briefing` + `/api/settings` |
| `config.json` | 你的配置（含 SendKey，已被 .gitignore 忽略） |
| `update-tasks.py` | 按课表注册计划任务（每节课前 30 分钟触发） |
| `install-task.ps1` | 注册每天固定时间的计划任务（无课表时用） |
| `index.html` 等 | PWA 前端，连上后端自动显示实时数据，连不上退化为演示模式 |

## 常见问题

- **微信收不到推送**：确认 `serverchan_sendkey` 正确，微信已关注 Server酱 公众号；用 `python briefing.py` 看报错。
- **地址解析失败**：把地址写得更具体（路名 + 邮编 + Singapore），或换成附近地标。
- **路线时长是畅通估算**：OSRM 免费但不知道拥堵；出门前点简报里的 Google Maps 链接看实时路况。
- **电脑睡眠导致没推送**：`install-task.ps1` 注册的任务开启了「唤醒运行」，但仍需接通电源、未关机；要 100% 可靠可部署到云服务器。

## 下一步（预留方向）

- Google Maps Directions API：接入后路况时长变成实时拥堵时长（需要 Google Cloud 免费 key）
- 网站订阅：把学校官网/新闻 RSS 加入简报（`build_briefing` 里扩展即可）
- Claude 智能总结：把订阅内容发给 Claude API，生成一句话摘要
- 云部署：迁移到服务器，24 小时稳定推送
