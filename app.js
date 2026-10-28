const STORAGE_KEY = "zaozhidao-settings";
const $ = (selector) => document.querySelector(selector);
const dialog = $("#settings-dialog");
const toast = $("#toast");
let toastTimeout;
let reminderTimeout;

const defaultSettings = {
  origin: "",
  destination: "",
  arrivalTime: "08:00",
  reminder: "07:00",
  notifications: false,
};

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return { ...defaultSettings, ...saved };
  } catch (error) {
    console.error("无法读取已保存的通勤设置。", error);
    return { ...defaultSettings };
  }
}

let settings = loadSettings();
let backendReady = false; // python server.py 是否在运行

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("show"), 3200);
}

function updateDate() {
  const now = new Date();
  const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "long" }).format(now);
  $("#today-label").textContent = `你的${weekday} · 早上好`;
  $("#date-day").textContent = String(now.getDate()).padStart(2, "0");
  $("#date-month").textContent = new Intl.DateTimeFormat("en", { month: "short" }).format(now);
}

// ---------- 后端数据 ----------

async function apiFetch(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`接口返回 ${response.status}`);
  return response.json();
}

async function connectBackend() {
  const remote = await apiFetch("/api/settings");
  backendReady = true;
  settings = {
    ...settings,
    origin: remote.origin || "",
    destination: remote.destination || "",
    arrivalTime: remote.arrival_time || defaultSettings.arrivalTime,
    reminder: remote.reminder || defaultSettings.reminder,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

const escapeHtml = (value) =>
  String(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

function renderSignals(signals) {
  const grid = $("#signals-list");
  grid.innerHTML = "";
  for (const signal of signals) {
    const card = document.createElement("article");
    card.className = "signal-card card";
    const action = signal.url
      ? `<a class="source-link" href="${escapeHtml(signal.url)}" target="_blank" rel="noopener noreferrer">打开链接 <span>↗</span></a>`
      : `<span class="source-link muted-link">${escapeHtml(signal.source || "")} <span>✳</span></span>`;
    card.innerHTML = `
      <div class="signal-topline"><span class="signal-category ${escapeHtml(signal.category)}">${escapeHtml(signal.label)}</span><span class="signal-time">${escapeHtml(signal.time || "")}</span></div>
      <h3>${escapeHtml(signal.title)}</h3>
      <p>${escapeHtml(signal.body)}</p>${action}`;
    grid.appendChild(card);
  }
}

function demoSignals() {
  return [
    {
      category: "campus",
      label: "校园通知",
      time: "08:12 · 示例",
      title: "本周课程与教室安排有更新",
      body: "示例摘要：出发前可查看学校教务处通知，确认今天的上课地点。",
      url: "https://www.google.com/search?q=%E6%95%99%E5%8A%A1%E5%A4%84%E9%80%9A%E7%9F%A5",
      source: "",
    },
    {
      category: "commute",
      label: "出行提醒",
      time: "07:55 · 示例",
      title: "早高峰给通勤多留一点时间",
      body: "示例摘要：通勤时段道路容易变慢，建议出发前在地图应用确认实时路线。",
      url: "https://uri.amap.com/",
      source: "",
    },
    {
      category: "daily",
      label: "今日提示",
      time: "07:40 · 示例",
      title: "别忘了带伞和校园卡",
      body: "这里可以汇总你订阅的网站、学校通知与个人待办，让出门前少一点遗漏。",
      url: "",
      source: "个人提醒 · 演示内容",
    },
  ];
}

function renderBriefing(data) {
  $("#banner-tag").textContent = "实时数据";
  $("#banner-text").textContent = data.summary;
  $("#commute-tag").textContent = "实时路况";
  $("#data-note").innerHTML =
    "<span>ⓘ</span> 天气来自 Open-Meteo，路线为畅通估算；出门前点开地图看实时路况。每天 " +
    escapeHtml(settings.reminder) +
    " 通过微信推送同一份简报。";

  if (data.weather) {
    const weather = data.weather;
    $("#weather-location").textContent = weather.location;
    $("#temperature").innerHTML = `${weather.temp}<span>°</span>`;
    $("#weather-condition").textContent = weather.condition;
    $("#weather-symbol").textContent = weather.symbol;
    $("#weather-range").textContent = `今日 ${weather.temp_min}° / ${weather.temp_max}°`;
    $("#wind-speed").textContent = `${weather.wind_kmh} km/h`;
    $("#precipitation").textContent = weather.rain_prob == null ? "暂无数据" : `${weather.rain_prob}%`;
    $("#weather-advice").textContent = weather.advice;
    $("#weather-updated").textContent = `更新于 ${data.generated_at}`;
  } else {
    $("#weather-location").textContent = "未获取到天气（检查后端配置）";
  }

  if (data.commute) {
    const commute = data.commute;
    $("#origin-label").textContent = settings.origin || "设置你的出发地";
    $("#destination-label").textContent = settings.destination || "设置学校地址";
    $("#commute-minutes").textContent = commute.duration_min;
    $("#commute-status").textContent = `${commute.congestion} · ${commute.distance_km} km`;
  }
  $("#map-button").href = data.map_url;
  $("#taxi-button").href = data.taxi_url;
  renderSignals(data.signals);
}

function renderFallback() {
  $("#banner-tag").textContent = "演示内容";
  $("#commute-tag").textContent = "路况演示";
  $("#commute-minutes").textContent = "—";
  $("#commute-status").textContent = "通勤时段可能较慢";
  $("#data-note").innerHTML =
    "<span>ⓘ</span> 当前为演示模式；启动后端 <code>python server.py</code> 后刷新即切换为实时数据。";
  updateRouteLinks();
  renderSignals(demoSignals());
}

async function refreshBriefing() {
  $("#banner-tag").textContent = "更新中…";
  try {
    renderBriefing(await apiFetch("/api/briefing"));
  } catch (error) {
    console.error("获取简报失败。", error);
    showToast("获取实时简报失败，请稍后重试。");
  }
}

// ---------- 设置与路线 ----------

function updateRouteLinks() {
  const origin = settings.origin.trim();
  const destination = settings.destination.trim();
  $("#origin-label").textContent = origin || "设置你的出发地";
  $("#destination-label").textContent = destination || "设置学校地址";
  const params = { callnative: "1", src: "zaozhidao|daily-assistant" };
  if (origin) params.from = origin;
  if (destination) params.to = destination;
  $("#taxi-button").href = `https://uri.amap.com/taxi?${new URLSearchParams(params)}`;
  $("#map-button").href = `https://uri.amap.com/navigation?${new URLSearchParams({ ...params, mode: "car" })}`;
}

function openSettings() {
  $("#origin-input").value = settings.origin;
  $("#destination-input").value = settings.destination;
  $("#arrival-input").value = settings.arrivalTime;
  $("#reminder-input").value = settings.reminder;
  $("#notification-input").checked = settings.notifications;
  dialog.showModal();
}

function scheduleReminder() {
  clearTimeout(reminderTimeout);
  if (!settings.notifications || Notification.permission !== "granted") return;

  const now = new Date();
  const [hours, minutes] = settings.reminder.split(":").map(Number);
  const next = new Date(now);
  next.setHours(hours, minutes, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);

  reminderTimeout = setTimeout(() => {
    new Notification("早知道 · 今日简报", {
      body: "微信已推送今天的天气与通勤简报，打开页面查看实时详情。",
      icon: "./icon.svg",
    });
    scheduleReminder();
  }, next.getTime() - now.getTime());
}

async function saveSettings(event) {
  event.preventDefault();
  const nextSettings = {
    origin: $("#origin-input").value.trim(),
    destination: $("#destination-input").value.trim(),
    arrivalTime: $("#arrival-input").value || "08:00",
    reminder: $("#reminder-input").value || "07:00",
    notifications: $("#notification-input").checked,
  };

  if (nextSettings.notifications) {
    if (!("Notification" in window)) {
      showToast("当前浏览器不支持通知，请以微信推送为准。");
      nextSettings.notifications = false;
    } else {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        nextSettings.notifications = false;
        showToast("未获得通知权限；微信推送不受影响。");
      }
    }
  }

  settings = nextSettings;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  updateRouteLinks();
  scheduleReminder();
  dialog.close();

  if (backendReady) {
    try {
      await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: settings.origin,
          destination: settings.destination,
          arrival_time: settings.arrivalTime,
          reminder: settings.reminder,
        }),
      });
      showToast("设置已同步到后端。若修改了推送时间，请重新运行 install-task.ps1。");
    } catch (error) {
      console.error("后端同步失败。", error);
      showToast("后端同步失败，设置仅保存在本地。");
    }
  } else {
    showToast("设置已保存（本地）。启动后端后自动同步。");
  }
}

// ---------- 天气（演示模式的定位兜底） ----------

function weatherDescription(code) {
  if (code === 0) return ["晴", "☀", "适合出门"];
  if ([1, 2].includes(code)) return ["晴间多云", "⛅", "带件外套"];
  if (code === 3) return ["阴", "☁", "注意保暖"];
  if ([45, 48].includes(code)) return ["有雾", "〰", "出行注意安全"];
  if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return ["有雨", "☂", "建议带伞"];
  if ([71, 73, 75, 77, 85, 86].includes(code)) return ["有雪", "❄", "注意路面湿滑"];
  if ([95, 96, 99].includes(code)) return ["有雷雨", "⛈", "留意天气变化"];
  return ["天气已更新", "☼", "出门注意安全"];
}

async function fetchWeather(latitude, longitude, locationName) {
  const endpoint = new URL("https://api.open-meteo.com/v1/forecast");
  endpoint.search = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    current: "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
    daily: "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    timezone: "auto",
    forecast_days: "1",
  });

  const response = await fetch(endpoint);
  if (!response.ok) throw new Error(`天气服务返回错误（${response.status}）`);
  const data = await response.json();
  if (!data.current || !data.daily) throw new Error("天气服务暂时没有返回完整数据。");

  const [condition, symbol, advice] = weatherDescription(data.current.weather_code);
  $("#weather-location").textContent = locationName;
  $("#temperature").innerHTML = `${Math.round(data.current.temperature_2m)}<span>°</span>`;
  $("#weather-condition").textContent = condition;
  $("#weather-symbol").textContent = symbol;
  $("#weather-range").textContent = `今日 ${Math.round(data.daily.temperature_2m_min[0])}° / ${Math.round(data.daily.temperature_2m_max[0])}°`;
  $("#wind-speed").textContent = `${Math.round(data.current.wind_speed_10m)} km/h`;
  const rainChance = data.daily.precipitation_probability_max?.[0];
  $("#precipitation").textContent = rainChance == null ? "暂无数据" : `${rainChance}%`;
  $("#weather-advice").textContent = advice;
  $("#weather-updated").textContent = `更新于 ${new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
}

async function locateWeather() {
  if (!navigator.geolocation) {
    showToast("此浏览器不支持定位，请启动后端查看配置地址的天气。");
    return;
  }
  $("#weather-location").textContent = "正在获取你的位置…";
  $("#locate-button").disabled = true;
  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,
        timeout: 10000,
        maximumAge: 300000,
      });
    });
    await fetchWeather(position.coords.latitude, position.coords.longitude, "你当前的位置");
  } catch (error) {
    console.error("获取天气失败。", error);
    $("#weather-location").textContent = "天气获取失败，请检查定位权限和网络连接";
    showToast(error.code ? "定位未成功，请检查浏览器的位置权限设置。" : error.message);
  } finally {
    $("#locate-button").disabled = false;
  }
}

// 后端在就刷新实时数据，不在就退回浏览器定位
async function handleLocate() {
  if (!backendReady) {
    try {
      await connectBackend();
    } catch {
      locateWeather();
      return;
    }
  }
  await refreshBriefing();
}

// ---------- 导航与初始化 ----------

function setupNavigation() {
  document.querySelectorAll(".nav-item").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      link.classList.add("active");
    });
  });
  $("#show-all-button").addEventListener("click", () => {
    showToast("这里汇总了天气、通勤与叫车直达；接入网站订阅后会出现更多来源。");
  });
}

async function init() {
  updateDate();
  try {
    await connectBackend();
    await refreshBriefing();
  } catch (error) {
    console.info("后端未连接，进入演示模式。", error);
    renderFallback();
  }
  updateRouteLinks();
  scheduleReminder();
  setupNavigation();

  $("#open-settings").addEventListener("click", openSettings);
  $("#close-settings").addEventListener("click", () => dialog.close());
  $("#cancel-settings").addEventListener("click", () => dialog.close());
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#locate-button").addEventListener("click", handleLocate);
  $("#refresh-button").addEventListener("click", handleLocate);
}

init();

if ("serviceWorker" in navigator && location.protocol !== "file:") {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch((error) => {
      console.error("离线缓存注册失败。", error);
    });
  });
}
