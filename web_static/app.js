const THEME_KEY = "pp-th-theme";
const PROXY_LS_KEY = "pp-th-proxy-raw";
const PROXY_ON_KEY = "pp-th-proxy-enabled";
const COUNTRY_KEY = "pp-th-country";
/** @type {Record<string, {placeholder:string, phone_cc?:string, name_zh?:string}>} */
let COUNTRY_META = {
  TH: { placeholder: "+66812345678", phone_cc: "+66", name_zh: "泰国" },
  JP: { placeholder: "+819012345678", phone_cc: "+81", name_zh: "日本" },
};

function setCountry(code) {
  const next = String(code || "TH").toUpperCase();
  const sel = document.querySelector("#countrySelect");
  if (sel) {
    if ([...sel.options].some((o) => o.value === next)) sel.value = next;
  }
  const country = sel?.value || next;
  const meta = COUNTRY_META[country] || COUNTRY_META.TH;
  const phone = document.querySelector("#phone");
  if (phone && meta) {
    // 区号/完整样例只作为 placeholder 示例；绝不改动用户已输入的 value
    const example = meta.placeholder || (meta.phone_cc ? `${meta.phone_cc}…` : "");
    phone.placeholder = example;
    phone.title = meta.phone_cc
      ? `示例区号 ${meta.phone_cc}；填写后显示完整手机号`
      : "示例号码；填写后显示完整手机号";
    // 明确：不设置 phone.value，避免覆盖用户输入
  }
  localStorage.setItem(COUNTRY_KEY, country);
}

async function loadRegions() {
  const sel = document.querySelector("#countrySelect");
  if (!sel) return;
  try {
    const data = await api("/api/regions");
    const regions = data.regions || [];
    if (regions.length) {
      COUNTRY_META = {};
      sel.innerHTML = regions.map((r) => {
        COUNTRY_META[r.code] = {
          placeholder: r.phone_placeholder || `${r.phone_cc || ""}…`,
          phone_cc: r.phone_cc,
          name_zh: r.name_zh,
        };
        const label = `${r.name_zh || r.code} ${r.code}${r.phone_cc ? " · " + r.phone_cc : ""}`;
        return `<option value="${esc(r.code)}">${esc(label)}</option>`;
      }).join("");
    }
  } catch (err) {
    // fallback static TH/JP already in HTML or empty
    if (!sel.options.length) {
      sel.innerHTML = '<option value="TH">泰国 TH · +66</option><option value="JP">日本 JP · +81</option>';
    }
  }
  const saved = localStorage.getItem(COUNTRY_KEY) || "TH";
  if ([...sel.options].some((o) => o.value === saved)) sel.value = saved;
  else if (sel.options.length) sel.selectedIndex = 0;
  setCountry(sel.value);
}

function loadCountryPref() {
  // regions filled async in loadRegions
  const sel = document.querySelector("#countrySelect");
  if (sel && sel.options.length) setCountry(sel.value || localStorage.getItem(COUNTRY_KEY) || "TH");
}

/** 规范化代理串：无协议时默认补 http://；host:port:user:pass 转为 http://user:pass@host:port */
function normalizeProxyInput(raw) {
  let value = String(raw || "").trim();
  if (!value) return "";
  if (/^(https?|socks5h?):\/\//i.test(value)) return value;
  // user:pass@host:port
  if (value.includes("@")) {
    return "http://" + value;
  }
  // host:port:user:pass (password may contain :)
  const parts = value.split(":");
  if (parts.length >= 4) {
    const host = parts[0].trim();
    const port = parts[1].trim();
    const user = parts[2].trim();
    const pass = parts.slice(3).join(":").trim();
    if (host && port && user && pass && /^\d+$/.test(port)) {
      return `http://${encodeURIComponent(user)}:${encodeURIComponent(pass)}@${host}:${port}`;
    }
  }
  // host:port
  if (/^[^:/\s]+:\d{1,5}$/.test(value)) {
    return "http://" + value;
  }
  return "http://" + value;
}

function getProxyForRequest() {
  if (!$("#proxyEnabled")?.checked) return "";
  return normalizeProxyInput($("#proxyRaw")?.value || "");
}

function setProxyTestResult(text, kind) {
  const el = $("#proxyTestResult");
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("ok", "bad", "pending");
  if (kind) el.classList.add(kind);
}

async function testProxy() {
  const btn = $("#testProxyBtn");
  const raw = ($("#proxyRaw")?.value || "").trim();
  if (!raw) {
    setProxyTestResult("请先填写代理", "bad");
    toast("请先填写代理信息");
    return;
  }
  const proxy = normalizeProxyInput(raw);
  // 回填规范化后的串（便于查看默认 http://）
  if ($("#proxyRaw") && proxy) $("#proxyRaw").value = proxy;
  saveProxyPrefs();
  if (btn) {
    btn.disabled = true;
    btn.textContent = "测试中…";
  }
  setProxyTestResult("测试中…", "pending");
  try {
    const data = await api("/api/proxy/test", {
      method: "POST",
      body: JSON.stringify({ proxy }),
    });
    const ip = data.exit_ip ? ` · IP ${data.exit_ip}` : "";
    const ms = data.latency_ms != null ? ` · ${data.latency_ms}ms` : "";
    setProxyTestResult(`可用${ip}${ms}`, "ok");
    toast("代理可用");
  } catch (err) {
    setProxyTestResult(`失败：${err.message}`, "bad");
    toast(err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "测试代理";
    }
  }
}


function syncProxyPanel() {
  const enabled = document.querySelector("#proxyEnabled")?.checked;
  const panel = document.querySelector("#proxyPanel");
  if (panel) panel.classList.toggle("hidden", !enabled);
  const input = document.querySelector("#proxyRaw");
  if (input) input.required = !!enabled;
}

function loadProxyPrefs() {
  const savedRaw = localStorage.getItem(PROXY_LS_KEY);
  const savedOn = localStorage.getItem(PROXY_ON_KEY);
  const rawEl = document.querySelector("#proxyRaw");
  const onEl = document.querySelector("#proxyEnabled");
  if (savedRaw != null && rawEl) rawEl.value = savedRaw;
  if (savedOn != null && onEl) onEl.checked = savedOn === "1";
  syncProxyPanel();
}

function saveProxyPrefs() {
  const rawEl = document.querySelector("#proxyRaw");
  const onEl = document.querySelector("#proxyEnabled");
  if (rawEl) localStorage.setItem(PROXY_LS_KEY, rawEl.value.trim());
  if (onEl) localStorage.setItem(PROXY_ON_KEY, onEl.checked ? "1" : "0");
}

const $ = (sel) => document.querySelector(sel);
const state = {
  currentJobId: localStorage.getItem("paypal-web-current-job") || "",
  pollTimer: null,
};

function fmtTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function fmtDuration(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ${s}s`;
}

function pretty(obj) {
  if (!obj) return "{}";
  return JSON.stringify(obj, null, 2);
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 2600);
}

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(THEME_KEY, next);
  const label = $("#themeLabel");
  if (label) label.textContent = next === "light" ? "浅色" : "深色";
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") {
    applyTheme(saved);
    return;
  }
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  applyTheme(prefersLight ? "light" : "dark");
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(cur === "dark" ? "light" : "dark");
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

function setServer(ok) {
  const el = $("#serverStatus");
  el.textContent = ok ? "ONLINE · 已连接" : "OFFLINE · 连接失败";
  el.classList.toggle("ok", ok);
  el.classList.toggle("bad", !ok);
}

async function health() {
  try {
    await api("/api/health");
    setServer(true);
  } catch (err) {
    setServer(false);
  }
}

async function refreshJobs() {
  try {
    const data = await api("/api/jobs");
    renderJobs(data.jobs || []);
  } catch (err) {
    toast(err.message);
  }
}

function renderJobs(jobs) {
  const box = $("#jobsList");
  if (!jobs.length) {
    box.className = "jobs-list empty";
    box.textContent = "暂无任务";
    return;
  }
  box.className = "jobs-list";
  box.innerHTML = jobs.map(job => `
    <div class="job-item ${job.id === state.currentJobId ? "active" : ""}" data-job-id="${esc(job.id)}">
      <div class="job-top">
        <span class="job-id">#${esc(job.id)}</span>
        <span class="badge ${esc(job.status)}">${esc(job.status)}</span>
      </div>
      <div class="job-sub">${esc(job.stage || "")}</div>
      <div class="job-sub">${esc(job.country || "TH")} · ${esc(job.ba_token || "")} · ${esc(fmtTime(job.created_at))} · ${job.proxy_enabled ? "代理开" : "代理关"}</div>
    </div>`).join("");
  box.querySelectorAll(".job-item").forEach(item => {
    item.addEventListener("click", () => selectJob(item.dataset.jobId));
  });
}

function selectJob(jobId) {
  state.currentJobId = jobId || "";
  if (jobId) localStorage.setItem("paypal-web-current-job", jobId);
  else localStorage.removeItem("paypal-web-current-job");
  refreshJobs();
  pollCurrent(true);
}

function renderLogs(logs) {
  const text = (logs || []).map(line => {
    const t = new Date((line.time || 0) * 1000).toLocaleTimeString();
    return `[${t}] ${line.level.padEnd(7)} ${line.message}`;
  }).join("\n");
  const box = $("#logsBox");
  box.textContent = text;
  if ($("#autoScroll").checked) box.scrollTop = box.scrollHeight;
}

function renderCurrent(job) {
  $("#currentEmpty").classList.add("hidden");
  $("#currentBody").classList.remove("hidden");
  $("#currentMeta").textContent = `#${job.id} · 创建于 ${fmtTime(job.created_at)} · ${job.proxy_label || "代理关闭"}`;
  $("#jobStatus").textContent = job.status;
  $("#jobStage").textContent = job.stage || "";
  $("#jobDuration").textContent = fmtDuration(job.duration);
  $("#generatedBox").textContent = pretty(job.generated);
  $("#resultBox").textContent = pretty(job.result || (job.error ? { error: job.error, traceback: job.traceback } : {}));
  $("#copyResult").disabled = !(job.result || job.error);

  const otpPanel = $("#otpPanel");
  otpPanel.classList.toggle("hidden", !job.awaiting_otp);
  $("#otpPrompt").textContent = job.awaiting_prompt || "请输入短信验证码或新手机号。";
  if (job.awaiting_otp) $("#otpValue").focus();

  renderLogs(job.logs || []);
}

async function pollCurrent(force = false) {
  if (!state.currentJobId) {
    $("#currentEmpty").classList.remove("hidden");
    $("#currentBody").classList.add("hidden");
    $("#currentMeta").textContent = "未选择任务";
    $("#copyResult").disabled = true;
    return;
  }
  try {
    const job = await api(`/api/jobs/${state.currentJobId}`);
    renderCurrent(job);
    if (force || ["completed", "failed", "awaiting_otp"].includes(job.status)) refreshJobs();
  } catch (err) {
    toast(err.message);
    state.currentJobId = "";
    localStorage.removeItem("paypal-web-current-job");
  }
}

async function startJob(evt) {
  evt.preventDefault();
  const btn = $("#startBtn");
  btn.disabled = true;
  const label = btn.querySelector("span:not(.btn-glow)") || btn;
  const prev = label.textContent;
  label.textContent = "启动中…";
  try {
    saveProxyPrefs();
    if ($("#proxyEnabled").checked && !$("#proxyRaw").value.trim()) {
      throw new Error("已启用代理，请填写代理信息");
    }
    const proxyNorm = getProxyForRequest();
    if ($("#proxyEnabled").checked && proxyNorm && $("#proxyRaw")) {
      $("#proxyRaw").value = proxyNorm;
      saveProxyPrefs();
    }
    const data = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        ba_token: $("#baToken").value,
        phone: $("#phone").value,
        max_card_attempts: Number($("#maxCardAttempts").value || 5),
        debug: $("#debug").checked,
        proxy_enabled: $("#proxyEnabled").checked,
        proxy: proxyNorm,
        country: $("#countrySelect") ? $("#countrySelect").value : "TH",
      }),
    });
    toast("任务已启动");
    selectJob(data.job.id);
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
    label.textContent = "开始执行";
  }
}

async function submitOtp(evt) {
  evt.preventDefault();
  if (!state.currentJobId) return;
  const value = $("#otpValue").value.trim();
  if (!value) return toast("请输入验证码或手机号");
  try {
    await api(`/api/jobs/${state.currentJobId}/otp`, {
      method: "POST",
      body: JSON.stringify({ value }),
    });
    $("#otpValue").value = "";
    toast("已提交");
    pollCurrent(true);
  } catch (err) {
    toast(err.message);
  }
}

async function copyResult() {
  if (!state.currentJobId) return;
  try {
    const job = await api(`/api/jobs/${state.currentJobId}`);
    await navigator.clipboard.writeText(pretty(job.result || { error: job.error, traceback: job.traceback }));
    toast("结果已复制");
  } catch (err) {
    toast(err.message);
  }
}

function bind() {
  $("#runForm").addEventListener("submit", startJob);
  $("#otpForm").addEventListener("submit", submitOtp);
  $("#refreshJobs").addEventListener("click", refreshJobs);
  $("#copyResult").addEventListener("click", copyResult);
  $("#clearCurrent").addEventListener("click", () => selectJob(""));
  const themeBtn = $("#themeToggle");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);
  const proxyEnabled = $("#proxyEnabled");
  if (proxyEnabled) {
    proxyEnabled.addEventListener("change", () => {
      syncProxyPanel();
      saveProxyPrefs();
    });
  }
  const proxyRaw = $("#proxyRaw");
  if (proxyRaw) {
    proxyRaw.addEventListener("change", () => {
      const v = proxyRaw.value.trim();
      if (v) proxyRaw.value = normalizeProxyInput(v);
      saveProxyPrefs();
    });
  }
  const countrySel = $("#countrySelect");
  if (countrySel) {
    countrySel.addEventListener("change", () => setCountry(countrySel.value));
  }
  const testBtn = $("#testProxyBtn");
  if (testBtn) testBtn.addEventListener("click", testProxy);
}

initTheme();
loadProxyPrefs();
bind();
loadRegions().catch(() => loadCountryPref());
health();
refreshJobs().then(() => pollCurrent(true));
setInterval(health, 8000);
setInterval(refreshJobs, 5000);
state.pollTimer = setInterval(() => pollCurrent(false), 1000);