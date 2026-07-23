const THEME_KEY = "pp-th-theme";
const PROXY_LS_KEY = "pp-th-proxy-raw";
const PROXY_ON_KEY = "pp-th-proxy-enabled";
const COUNTRY_KEY = "pp-th-country";
const FP_KEY = "pp-th-fingerprint-source";
const DD_KEY = "pp-th-datadome-mode";
const MTR_KEY = "pp-th-mtr-runtime";
const RUNTIME_KEY = "pp-th-runtime"; // legacy coarse mode
const ROXY_KEY_KEY = "pp-th-roxy-api-key";
const ROXY_HOST_KEY = "pp-th-roxy-api-host";
const ROXY_PORT_KEY = "pp-th-roxy-api-port";
const ROXY_HEADLESS_KEY = "pp-th-roxy-headless";
const ROXY_WS_KEY = "pp-th-roxy-workspace-id";
const ROXY_PJ_KEY = "pp-th-roxy-project-id";
const SMSBOWER_ON_KEY = "pp-th-smsbower-on";
const PROFILE_KEY = "pp-th-profile";
const MERCHANT_KEY = "pp-th-continue-merchant";
const COUNTRY_NAME_ZH = {
  TH: "\u6cf0\u56fd",
  JP: "\u65e5\u672c",
  US: "\u7f8e\u56fd",
  GB: "\u82f1\u56fd",
  BR: "\u5df4\u897f",
  MX: "\u58a8\u897f\u54e5",
  ID: "\u5370\u5ea6\u5c3c\u897f\u4e9a",
  MY: "\u9a6c\u6765\u897f\u4e9a",
  SG: "\u65b0\u52a0\u5761",
  PH: "\u83f2\u5f8b\u5bbe",
  VN: "\u8d8a\u5357",
  KR: "\u97e9\u56fd",
  HK: "\u9999\u6e2f",
  TW: "\u53f0\u6e7e",
  CN: "\u4e2d\u56fd",
  AU: "\u6fb3\u5927\u5229\u4e9a",
  NZ: "\u65b0\u897f\u5170",
  CA: "\u52a0\u62ff\u5927",
  DE: "\u5fb7\u56fd",
  FR: "\u6cd5\u56fd",
  ES: "\u897f\u73ed\u7259",
  IT: "\u610f\u5927\u5229",
  NL: "\u8377\u5170",
  SE: "\u745e\u5178",
  PL: "\u6ce2\u5170",
  PT: "\u8461\u8404\u7259",
  IE: "\u7231\u5c14\u5170",
  CH: "\u745e\u58eb",
  AT: "\u5965\u5730\u5229",
  BE: "\u6bd4\u5229\u65f6",
  DK: "\u4e39\u9ea6",
  NO: "\u632a\u5a01",
  FI: "\u82ac\u5170",
  IN: "\u5370\u5ea6",
  AE: "\u963f\u8054\u914b",
  SA: "\u6c99\u7279\u963f\u62c9\u4f2f",
  IL: "\u4ee5\u8272\u5217",
  TR: "\u571f\u8033\u5176",
  RU: "\u4fc4\u7f57\u65af",
  ZA: "\u5357\u975e",
  AR: "\u963f\u6839\u5ef7",
  CL: "\u667a\u5229",
  CO: "\u54e5\u4f26\u6bd4\u4e9a",
  PE: "\u79d8\u9c81"
};
/** @type {Record<string, {placeholder:string, phone_cc?:string, name_zh?:string, code?:string}>} */
let COUNTRY_META = {
  TH: { placeholder: "+66812345678", phone_cc: "+66", name_zh: COUNTRY_NAME_ZH.TH, code: "TH" },
  JP: { placeholder: "+819012345678", phone_cc: "+81", name_zh: COUNTRY_NAME_ZH.JP, code: "JP" },
};
/** @type {Array<{code:string, name_zh:string, phone_cc:string, placeholder:string}>} */
let COUNTRY_OPTIONS = [];

function getSelectedCountry() {
  const hidden = document.querySelector("#countrySelect");
  return String(hidden?.value || localStorage.getItem(COUNTRY_KEY) || "TH").toUpperCase();
}

function countryDisplayLabel(meta) {
  const code = String((meta && (meta.code || meta.country)) || "").toUpperCase();
  return resolveCountryNameZh(code, meta && meta.name_zh);
}

function resolveCountryNameZh(code, fallback) {
  const c = String(code || "").toUpperCase();
  const fb = String(fallback || "").trim();
  if (COUNTRY_NAME_ZH[c]) return COUNTRY_NAME_ZH[c];
  // Never show English-only labels in the country list
  if (fb && !/^[A-Za-z][A-Za-z\s.'-]+$/.test(fb)) return fb;
  return c || COUNTRY_NAME_ZH.TH || "TH";
}


function setCountry(code) {
  const next = String(code || "TH").toUpperCase();
  const hidden = document.querySelector("#countrySelect");
  const search = document.querySelector("#countrySearch");
  const meta = COUNTRY_META[next] || COUNTRY_META.TH || { name_zh: next, phone_cc: "", placeholder: "" };
  if (hidden) hidden.value = next;
  if (search) search.value = countryDisplayLabel(meta);
  const phone = document.querySelector("#phone");
  if (phone && meta) {
    phone.placeholder = meta.placeholder || meta.phone_cc || "";
    phone.title = meta.phone_cc ? `区号 ${meta.phone_cc}，填写完整手机号` : "填写完整手机号";
  }
  localStorage.setItem(COUNTRY_KEY, next);
  return next;
}

function filterCountries(query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return COUNTRY_OPTIONS.slice();
  return COUNTRY_OPTIONS.filter((r) => {
    const zh = String(resolveCountryNameZh(r.code, r.name_zh) || "").toLowerCase();
    const code = String(r.code || "").toLowerCase();
    const cc = String(r.phone_cc || "").toLowerCase();
    const q2 = q.replace("+", "");
    return zh.includes(q) || code.includes(q) || cc.includes(q) || cc.replace("+", "").includes(q2);
  });
}


function renderCountryList(items, activeCode) {
  const list = document.querySelector("#countryList");
  if (!list) return;
  if (!items.length) {
    list.innerHTML = `<li class="empty">无匹配国家</li>`;
    return;
  }
  list.innerHTML = items
    .map((r) => {
      const active = r.code === activeCode ? " active" : "";
      return `<li class="${active}" role="option" data-code="${esc(r.code)}" aria-selected="${r.code === activeCode}">${esc(resolveCountryNameZh(r.code, r.name_zh))}</li>`;
    })
    .join("");
}


function isCountryListOpen() {
  const list = document.querySelector("#countryList");
  return !!(list && !list.hidden);
}

function openCountryList(opts = {}) {
  const list = document.querySelector("#countryList");
  const search = document.querySelector("#countrySearch");
  const combo = document.querySelector("#countryCombo");
  if (!list || !search) return;
  const selected = getSelectedCountry();
  const selectedLabel = countryDisplayLabel(COUNTRY_META[selected]);
  const q = String(search.value || "").trim();
  // Dropdown click / toggle: show full list. Typing filter: show matches.
  const forceAll = !!opts.all;
  const items = (!forceAll && q && q !== selectedLabel) ? filterCountries(q) : COUNTRY_OPTIONS.slice();
  renderCountryList(items, selected);
  list.hidden = false;
  search.setAttribute("aria-expanded", "true");
  if (combo) combo.classList.add("open");
  if (opts.focus !== false) {
    search.focus();
    if (opts.select !== false && (!q || q === selectedLabel)) search.select();
  }
}

function closeCountryList() {
  const list = document.querySelector("#countryList");
  const search = document.querySelector("#countrySearch");
  const combo = document.querySelector("#countryCombo");
  if (list) list.hidden = true;
  if (search) search.setAttribute("aria-expanded", "false");
  if (combo) combo.classList.remove("open");
  // Snap display back to Chinese name of current selection
  setCountry(getSelectedCountry());
}

function toggleCountryList() {
  if (isCountryListOpen()) closeCountryList();
  else openCountryList({ all: true });
}

function bindCountryCombo() {
  const combo = document.querySelector("#countryCombo");
  const search = document.querySelector("#countrySearch");
  const list = document.querySelector("#countryList");
  const toggle = document.querySelector("#countryToggle");
  if (!combo || !search || !list || combo.dataset.bound === "1") return;
  combo.dataset.bound = "1";

  // Click field: open full dropdown (still editable for search)
  search.addEventListener("click", () => {
    openCountryList({ all: true });
  });
  search.addEventListener("focus", () => {
    if (!isCountryListOpen()) openCountryList({ all: true });
  });
  // Type: filter list live
  search.addEventListener("input", () => {
    const q = search.value;
    renderCountryList(filterCountries(q), getSelectedCountry());
    list.hidden = false;
    search.setAttribute("aria-expanded", "true");
    combo.classList.add("open");
  });
  search.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!isCountryListOpen()) openCountryList({ all: true, select: false });
    }
    const items = [...list.querySelectorAll("li[data-code]")];
    let idx = items.findIndex((el) => el.classList.contains("active"));
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!items.length) return;
      idx = Math.min(items.length - 1, (idx < 0 ? -1 : idx) + 1);
      items.forEach((el, i) => el.classList.toggle("active", i === idx));
      items[idx]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!items.length) return;
      idx = Math.max(0, idx < 0 ? 0 : idx - 1);
      items.forEach((el, i) => el.classList.toggle("active", i === idx));
      items[idx]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      const cur = (idx >= 0 ? items[idx] : null) || items[0];
      if (cur) {
        setCountry(cur.dataset.code);
        closeCountryList();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeCountryList();
      search.blur();
    }
  });
  if (toggle) {
    toggle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleCountryList();
    });
  }
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-code]");
    if (!li) return;
    e.preventDefault();
    setCountry(li.dataset.code);
    closeCountryList();
  });
  document.addEventListener("click", (e) => {
    if (!combo.contains(e.target)) closeCountryList();
  });
}

async function loadRegions() {
  const hidden = document.querySelector("#countrySelect");
  if (!hidden) return;
  bindCountryCombo();
  try {
    const data = await api("/api/regions");
    const regions = data.regions || [];
    if (regions.length) {
      COUNTRY_META = {};
      COUNTRY_OPTIONS = regions.map((r) => {
        const code = String(r.code || "").toUpperCase();
        const item = {
          code,
          name_zh: resolveCountryNameZh(code, r.name_zh || ""),
          phone_cc: r.phone_cc || "",
          placeholder: r.phone_placeholder || r.phone_cc || "",
        };
        COUNTRY_META[code] = item;
        return item;
      });
    }
  } catch (err) {
    if (!COUNTRY_OPTIONS.length) {
      COUNTRY_OPTIONS = Object.keys(COUNTRY_NAME_ZH).map((code) => ({
        code,
        name_zh: COUNTRY_NAME_ZH[code],
        phone_cc: "",
        placeholder: "",
      }));
      COUNTRY_META = Object.fromEntries(COUNTRY_OPTIONS.map((x) => [x.code, x]));
    }
  }
  COUNTRY_OPTIONS = COUNTRY_OPTIONS.map((r) => ({
    ...r,
    name_zh: resolveCountryNameZh(r.code, r.name_zh),
  }));
  COUNTRY_META = Object.fromEntries(COUNTRY_OPTIONS.map((x) => [x.code, x]));
  const saved = localStorage.getItem(COUNTRY_KEY) || "TH";
  const code = COUNTRY_META[saved] ? saved : COUNTRY_OPTIONS[0]?.code || "TH";
  setCountry(code);
}

function loadCountryPref() {
  const code = getSelectedCountry();
  if (COUNTRY_META[code] || COUNTRY_OPTIONS.length) setCountry(code);
}

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
  saveProxyPrefs();
  const raw = ($("#proxyRaw")?.value || "").trim();
  if (!raw) {
    setProxyTestResult("请先填写代理", "bad");
    return;
  }
  const proxy = normalizeProxyInput(raw);
  if ($("#proxyRaw") && proxy) $("#proxyRaw").value = proxy;
  saveProxyPrefs();
  if (btn) btn.disabled = true;
  setProxyTestResult("测试中…", "pending");
  try {
    const data = await api("/api/proxy/test", {
      method: "POST",
      body: JSON.stringify({ proxy, proxy_mode: "custom" }),
    });
    if (data.ok === false) {
      setProxyTestResult(`失败：${data.message || data.error || "不可用"}`, "bad");
    } else {
      const ip = data.exit_ip ? ` · IP ${data.exit_ip}` : "";
      const ms = data.latency_ms != null ? ` · ${data.latency_ms}ms` : "";
      setProxyTestResult(`可用${ip}${ms}`, "ok");
    }
  } catch (err) {
    setProxyTestResult(`失败：${err.message}`, "bad");
  } finally {
    if (btn) btn.disabled = false;
  }
}




function syncProxyPanel() {
  const enabled = document.querySelector("#proxyEnabled")?.checked;
  const panel = document.querySelector("#proxyPanel");
  if (panel) panel.classList.toggle("hidden", !enabled);
  const rawWrap = document.querySelector("#proxyRawWrap");
  if (rawWrap) rawWrap.classList.remove("hidden");
  const input = document.querySelector("#proxyRaw");
  if (input) {
    input.required = !!enabled;
    input.disabled = !enabled;
  }
}




function setSelectIfValid(sel, value, fallback) {
  if (!sel) return;
  const v = String(value || fallback || "").trim();
  if ([...sel.options].some((o) => o.value === v)) sel.value = v;
  else if (fallback) sel.value = fallback;
}

function normalizeFingerprintSource(v) {
  const x = String(v || "headless").trim().toLowerCase().replace(/-/g, "_");
  if (["headless", "roxy", "random", "auto"].includes(x)) return x;
  if (x === "program" || x === "python" || x === "synthetic") return "random";
  if (x === "browser") return "roxy";
  return "headless";
}

function normalizeDatadomeMode(v) {
  const x = String(v || "headless").trim().toLowerCase().replace(/-/g, "_");
  if (["headless", "roxy", "protocol", "auto", "off"].includes(x)) return x;
  if (x === "edge") return "protocol";
  if (x === "browser") return "roxy";
  return "headless";
}

function normalizeMtrRuntime(v) {
  const x = String(v || "headless").trim().toLowerCase().replace(/-/g, "_");
  if (["headless", "roxy", "python_generated", "auto", "block", "off"].includes(x)) return x;
  if (x === "python" || x === "protocol") return "python_generated";
  if (x === "browser") return "roxy";
  return "headless";
}


function needsRoxyConfig() {
  const modes = [
    normalizeFingerprintSource($("#fingerprintSource")?.value || "headless"),
    normalizeDatadomeMode($("#datadomeMode")?.value || "headless"),
    normalizeMtrRuntime($("#mtrRuntime")?.value || "headless"),
  ];
  return modes.some((m) => m === "roxy" || m === "auto");
}

function syncRoxyPanel() {
  const panel = document.querySelector("#roxyPanel");
  if (!panel) return;
  const need = needsRoxyConfig();
  panel.classList.toggle("hidden", !need);
  const keyEl = document.querySelector("#roxyApiKey");
  if (keyEl) keyEl.required = need && !(keyEl.value || "").trim();
}

function loadRoxyPrefs() {
  try {
    const key = localStorage.getItem(ROXY_KEY_KEY);
    const host = localStorage.getItem(ROXY_HOST_KEY);
    const port = localStorage.getItem(ROXY_PORT_KEY);
    const headless = localStorage.getItem(ROXY_HEADLESS_KEY);
    const ws = localStorage.getItem(ROXY_WS_KEY);
    const pj = localStorage.getItem(ROXY_PJ_KEY);
    if (key != null && $("#roxyApiKey")) $("#roxyApiKey").value = key;
    if (host != null && $("#roxyApiHost")) $("#roxyApiHost").value = host || "127.0.0.1";
    if (port != null && $("#roxyApiPort")) $("#roxyApiPort").value = port || "50000";
    if (headless != null && $("#roxyHeadless")) $("#roxyHeadless").checked = headless !== "0";
    if (ws != null && $("#roxyWorkspaceId")) $("#roxyWorkspaceId").value = ws;
    if (pj != null && $("#roxyProjectId")) $("#roxyProjectId").value = pj;
  } catch (e) {}
  syncRoxyPanel();
}

function saveRoxyPrefs() {
  try {
    if ($("#roxyApiKey")) localStorage.setItem(ROXY_KEY_KEY, ($("#roxyApiKey").value || "").trim());
    if ($("#roxyApiHost")) localStorage.setItem(ROXY_HOST_KEY, ($("#roxyApiHost").value || "127.0.0.1").trim() || "127.0.0.1");
    if ($("#roxyApiPort")) localStorage.setItem(ROXY_PORT_KEY, String($("#roxyApiPort").value || "50000"));
    if ($("#roxyHeadless")) localStorage.setItem(ROXY_HEADLESS_KEY, $("#roxyHeadless").checked ? "1" : "0");
    if ($("#roxyWorkspaceId")) localStorage.setItem(ROXY_WS_KEY, ($("#roxyWorkspaceId").value || "").trim());
    if ($("#roxyProjectId")) localStorage.setItem(ROXY_PJ_KEY, ($("#roxyProjectId").value || "").trim());
  } catch (e) {}
}

function getRoxyConfigPayload() {
  if (!needsRoxyConfig()) {
    return {
      roxy_api_key: "",
      roxy_api_host: "",
      roxy_api_port: 0,
      roxy_headless: true,
      roxy_workspace_id: "",
      roxy_project_id: "",
    };
  }
  return {
    roxy_api_key: ($("#roxyApiKey")?.value || "").trim(),
    roxy_api_host: ($("#roxyApiHost")?.value || "127.0.0.1").trim() || "127.0.0.1",
    roxy_api_port: Number($("#roxyApiPort")?.value || 50000) || 50000,
    roxy_headless: $("#roxyHeadless") ? $("#roxyHeadless").checked : true,
    roxy_workspace_id: ($("#roxyWorkspaceId")?.value || "").trim(),
    roxy_project_id: ($("#roxyProjectId")?.value || "").trim(),
  };
}

function setRoxyTestResult(text, kind) {
  const el = $("#roxyTestResult");
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("ok", "bad", "pending");
  if (kind) el.classList.add(kind);
}

async function testRoxy() {
  const btn = document.querySelector("#testRoxyBtn");
  saveRoxyPrefs();
  const cfg = getRoxyConfigPayload();
  if (!cfg.roxy_api_key) {
    setRoxyTestResult("请填写 API Key", "bad");
    document.querySelector("#roxyApiKey")?.focus();
    return;
  }
  if (btn) btn.disabled = true;
  setRoxyTestResult("测试中…", "pending");
  try {
    const data = await api("/api/roxy/test", {
      method: "POST",
      body: JSON.stringify(cfg),
    });
    const msg = data.message || data.detail || "连接成功";
    setRoxyTestResult(msg, data.ok === false ? "bad" : "ok");
  } catch (err) {
    setRoxyTestResult("失败：" + (err.message || err), "bad");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function normalizeBuyerIdentityMode(value) {
  const v = String(value || "legacy").trim().toLowerCase().replace(/-/g, "_");
  if (["elevate_bind", "guest_elevate", "bind_ec", "elevate", "guest_bind", "bind", "v2"].includes(v)) {
    return "elevate_bind";
  }
  return "legacy";
}

function getRuntimePayload() {
  return {
    fingerprint_source: normalizeFingerprintSource($("#fingerprintSource")?.value || "headless"),
    datadome_mode: normalizeDatadomeMode($("#datadomeMode")?.value || "headless"),
    mtr_runtime: normalizeMtrRuntime($("#mtrRuntime")?.value || "headless"),
    buyer_identity_mode: normalizeBuyerIdentityMode($("#buyerIdentityMode")?.value || "legacy"),
  };
}

function loadRuntimePrefs() {
  try {
    // Brazil Web: runtime selects use HTML defaults (headless), not localStorage.
    // Clear legacy sticky auto/roxy prefs so UI matches Brazil default on refresh.
    try {
      localStorage.removeItem(FP_KEY);
      localStorage.removeItem(DD_KEY);
      localStorage.removeItem(MTR_KEY);
      localStorage.removeItem(RUNTIME_KEY);
    } catch (e0) {}
    setSelectIfValid(document.querySelector("#fingerprintSource"), "headless", "headless");
    setSelectIfValid(document.querySelector("#datadomeMode"), "headless", "headless");
    setSelectIfValid(document.querySelector("#mtrRuntime"), "headless", "headless");
    const sb = localStorage.getItem(SMSBOWER_ON_KEY);
    if (sb != null && document.querySelector("#smsbowerEnabled")) {
      document.querySelector("#smsbowerEnabled").checked = sb === "1";
    }
  } catch (e) {}
}

function saveRuntimePrefs() {
  try {
    // Do not persist fingerprint/datadome/mtr (Brazil behavior).
    localStorage.setItem(PROFILE_KEY, "real");
    localStorage.setItem(MERCHANT_KEY, "0");
    if ($("#smsbowerEnabled")) {
      localStorage.setItem(SMSBOWER_ON_KEY, $("#smsbowerEnabled").checked ? "1" : "0");
    }
  } catch (e) {}
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
  const buyerLabel = (job.buyer_identity_mode === "elevate_bind") ? "升Guest绑EC" : "原版";
  const runtimeMeta = ` · FP:${job.fingerprint_source || "-"} · DD:${job.datadome_mode || "-"} · MTR:${job.mtr_runtime || "-"} · Buyer:${buyerLabel}`;
  $("#currentMeta").textContent = `#${job.id} · 创建于 ${fmtTime(job.created_at)} · ${job.proxy_label || "代理关闭"}${runtimeMeta}`;
  $("#jobStatus").textContent = job.status;
  $("#jobStage").textContent = job.stage || "";
  $("#jobDuration").textContent = fmtDuration(job.duration);
  $("#generatedBox").textContent = pretty(job.generated);
  $("#resultBox").textContent = pretty(job.result || (job.error ? { error: job.error, traceback: job.traceback } : {}));
  $("#copyResult").disabled = !(job.result || job.error);

  const otpPanel = $("#otpPanel");
  const wasAwaiting = !otpPanel.classList.contains("hidden");
  const nowAwaiting = !!job.awaiting_otp;
  otpPanel.classList.toggle("hidden", !nowAwaiting);
  $("#otpPrompt").textContent = job.awaiting_prompt || "请输入短信验证码，或输入【新的】手机号重新发送。";
  if (nowAwaiting) {
    // 首次进入等待态时清空，避免浏览器把上方手机号自动填进验证码框
    if (!wasAwaiting) {
      $("#otpValue").value = "";
    }
    const otpInput = $("#otpValue");
    if (otpInput) {
      otpInput.setAttribute("autocomplete", "one-time-code");
      otpInput.setAttribute("name", "paypal_otp_or_new_phone");
      otpInput.setAttribute("inputmode", "text");
      otpInput.setAttribute("autocapitalize", "off");
      otpInput.setAttribute("autocorrect", "off");
      otpInput.setAttribute("spellcheck", "false");
    }
    $("#otpValue").focus();
  }

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
    saveRuntimePrefs();
    saveRoxyPrefs();
    if (needsRoxyConfig()) {
      const rk = ($("#roxyApiKey")?.value || "").trim();
      if (!rk) throw new Error("已选择 Roxy/自动，请填写 Roxy API Key");
    }
    try {
      if ($('#smsbowerEnabled')) localStorage.setItem(SMSBOWER_ON_KEY, $('#smsbowerEnabled').checked ? '1' : '0');
    } catch (e) {}
    if ($("#proxyEnabled").checked && !$("#proxyRaw").value.trim()) {
      throw new Error("已启用代理，请填写代理信息");
    }
    const proxyNorm = getProxyForRequest();
    if ($("#proxyEnabled").checked && proxyNorm && $("#proxyRaw")) {
      $("#proxyRaw").value = proxyNorm;
      saveProxyPrefs();
    saveRuntimePrefs();
    try {
      if ($('#smsbowerEnabled')) localStorage.setItem(SMSBOWER_ON_KEY, $('#smsbowerEnabled').checked ? '1' : '0');
    } catch (e) {}
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
        country: getSelectedCountry(),
                ...getRuntimePayload(),
        ...getRoxyConfigPayload(),
        max_flow_attempts: Number($("#maxFlowAttempts")?.value || 1),
        max_authorize_attempts: Number($("#maxAuthorizeAttempts")?.value || 3),
        card_retry_delay_seconds: Number($("#cardRetryDelay")?.value || 6),
        card_retry_jitter_seconds: Number($("#cardRetryJitter")?.value || 2),
        profile: "real",
        continue_merchant: false,
        smsbower_enabled: $("#smsbowerEnabled") ? $("#smsbowerEnabled").checked : false,
        smsbower_api_key: $("#smsbowerApiKey") ? $("#smsbowerApiKey").value.trim() : "",
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
    saveRuntimePrefs();
    try {
      if ($('#smsbowerEnabled')) localStorage.setItem(SMSBOWER_ON_KEY, $('#smsbowerEnabled').checked ? '1' : '0');
    } catch (e) {}
    });
  }
  const proxyRaw = $("#proxyRaw");
  if (proxyRaw) {
    proxyRaw.addEventListener("change", () => {
      const v = proxyRaw.value.trim();
      if (v) proxyRaw.value = normalizeProxyInput(v);
      saveProxyPrefs();
    saveRuntimePrefs();
    try {
      if ($('#smsbowerEnabled')) localStorage.setItem(SMSBOWER_ON_KEY, $('#smsbowerEnabled').checked ? '1' : '0');
    } catch (e) {}
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
  loadRuntimePrefs();
["#fingerprintSource","#datadomeMode","#mtrRuntime"].forEach((id) => {
  const el = document.querySelector(id);
  if (el) el.addEventListener("change", () => {
    saveRuntimePrefs();
    syncRoxyPanel();
  });
});
if ($("#testRoxyBtn")) $("#testRoxyBtn").addEventListener("click", testRoxy);
["#roxyApiKey","#roxyApiHost","#roxyApiPort","#roxyHeadless","#roxyWorkspaceId","#roxyProjectId"].forEach((id) => {
  const el = document.querySelector(id);
  if (el) el.addEventListener("change", saveRoxyPrefs);
});
syncRoxyPanel();
try {
  const rt = localStorage.getItem(RUNTIME_KEY);
  const sb = localStorage.getItem(SMSBOWER_ON_KEY);
  if (sb != null && document.querySelector('#smsbowerEnabled')) document.querySelector('#smsbowerEnabled').checked = sb === '1';
} catch (e) {}
bind();
loadRegions().catch(() => loadCountryPref());
health();
refreshJobs().then(() => pollCurrent(true));
setInterval(health, 8000);
setInterval(refreshJobs, 5000);
state.pollTimer = setInterval(() => pollCurrent(false), 1000);