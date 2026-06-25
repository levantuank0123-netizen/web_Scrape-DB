// Affiliate Dashboard - Static frontend (Netlify)
// Fetches data from Apps Script webhook (Google Sheet bound).

// ============ CONFIG ============
const WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz-rkOBF08lVO1xfpzQPs-CFm8pTRN-OGWS_H6pHo5yx1KP7WrS-EVni_fIaAQ5Cjs5jQ/exec";

const PLATFORM_META = {
  getrewardful:  { name: "Rewardful",     gradient: "from-emerald-500 to-teal-700",  icon: "🟢", status: "active",
                   metricLabels: ["Visitors","Leads","Conv."], moneyLabels: ["Unpaid","Paid","Earned","Due Now"] },
  firstpromoter: { name: "FirstPromoter", gradient: "from-pink-500 to-rose-700",     icon: "🌸", status: "active",
                   metricLabels: ["Clicks","Refs","Customers"], moneyLabels: ["Due 6d","Unpaid","Paid","Pending"] },
  tolt:          { name: "Tolt",          gradient: "from-blue-500 to-indigo-700",   icon: "🔵", status: "coming" },
  goaffpro:      { name: "GoAffPro",      gradient: "from-green-500 to-emerald-700", icon: "🟩", status: "active",
                   metricLabels: ["Clicks","Refs","Orders"], moneyLabels: ["Earned","Unpaid","Due Now","Paid"] },
  uppromote:     { name: "UpPromote",     gradient: "from-orange-500 to-amber-700",  icon: "🟧", status: "coming" },
  impact:        { name: "Impact",        gradient: "from-cyan-500 to-blue-700",     icon: "🔷", status: "coming" },
  partnerstack:  { name: "PartnerStack",  gradient: "from-violet-500 to-purple-700", icon: "🟣", status: "coming" },
  dub:           { name: "Dub.co",        gradient: "from-slate-500 to-gray-700",    icon: "⬛", status: "coming" },
  reditus:       { name: "Reditus",       gradient: "from-fuchsia-500 to-pink-700",  icon: "🟪", status: "coming" },
  tapfiliate:    { name: "Tapfiliate",    gradient: "from-yellow-500 to-orange-600", icon: "🟨", status: "coming" },
  trackdesk:     { name: "Trackdesk",     gradient: "from-red-500 to-rose-600",      icon: "🟥", status: "coming" },
};

// ============ STATE ============
let TOKEN = localStorage.getItem("aff_token") || "";
let USERNAME = localStorage.getItem("aff_user") || "";
let CURRENT_DATE = null;
let CACHE = {}; // {date: {platform: [rows]}}

// ============ AUTH ============
async function login(username, password) {
  const url = new URL(WEBHOOK_URL);
  url.searchParams.set("action", "login");
  url.searchParams.set("user", username);
  url.searchParams.set("pass", password);
  const res = await fetch(url.toString());
  const data = await res.json();
  if (data.ok) {
    TOKEN = data.token;
    USERNAME = username;
    localStorage.setItem("aff_token", TOKEN);
    localStorage.setItem("aff_user", USERNAME);
    return true;
  }
  return false;
}

function logout() {
  TOKEN = ""; USERNAME = "";
  localStorage.removeItem("aff_token");
  localStorage.removeItem("aff_user");
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login-screen").classList.remove("hidden");
}

// ============ API ============
async function apiGet(action, params = {}) {
  const url = new URL(WEBHOOK_URL);
  url.searchParams.set("action", action);
  url.searchParams.set("token", TOKEN);
  for (const k of Object.keys(params)) url.searchParams.set(k, params[k]);
  const res = await fetch(url.toString());
  const data = await res.json();
  if (data.error === "unauthorized") {
    logout();
    throw new Error("Session hết hạn, login lại.");
  }
  return data;
}

// ============ DATA ============
async function loadDates() {
  const d = await apiGet("dates");
  return d.dates || [];
}

async function loadData(date) {
  if (CACHE[date]) return CACHE[date];
  const d = await apiGet("data", { date });
  CACHE[date] = d;
  return d;
}

function computeSummary(data) {
  const result = [];
  for (const key of Object.keys(PLATFORM_META)) {
    const meta = PLATFORM_META[key];
    const rows = (data && data[key]) || [];
    const success = rows.filter(r => !r.error).length;
    const fail = rows.length - success;
    const totalClicks = rows.reduce((s,r) => s + (Number(r.clicks)||0), 0);
    const totalUnpaid = rows.reduce((s,r) => s + (Number(r.unpaid)||0), 0);
    const totalDueNow = rows.reduce((s,r) => s + (Number(r.due_now)||0), 0);
    const totalPending = rows.reduce((s,r) => s + (Number(r.pending_amount)||0), 0);
    result.push({
      key, ...meta,
      total: rows.length, success, fail,
      total_clicks: totalClicks,
      total_unpaid: totalUnpaid,
      total_due_now: totalDueNow,
      total_pending: totalPending,
    });
  }
  return result;
}

// ============ RENDER ============
function renderKPI(summary) {
  const total = summary.reduce((s,x) => s + x.total, 0);
  const success = summary.reduce((s,x) => s + x.success, 0);
  const fail = summary.reduce((s,x) => s + x.fail, 0);
  const unpaid = summary.reduce((s,x) => s + x.total_unpaid, 0);
  const dueNow = summary.reduce((s,x) => s + x.total_due_now, 0);
  const pending = summary.reduce((s,x) => s + x.total_pending, 0);
  const rate = total ? (100 * success / total).toFixed(1) : 0;
  document.getElementById("kpi-row").innerHTML = `
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div class="text-xs text-muted uppercase">Total dashboards</div>
      <div class="text-3xl font-bold mt-1">${total}</div>
      <div class="text-xs text-muted mt-2">Date: ${CURRENT_DATE}</div>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div class="text-xs text-muted uppercase">Success rate</div>
      <div class="text-3xl font-bold mt-1 text-emerald-400">${rate}%</div>
      <div class="text-xs text-muted mt-2">${success} ok / ${fail} lỗi</div>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div class="text-xs text-muted uppercase">Total Unpaid</div>
      <div class="text-3xl font-bold mt-1 text-amber-400">$${unpaid.toFixed(2)}</div>
      <div class="text-xs text-muted mt-2">Approved chưa pay</div>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div class="text-xs text-muted uppercase">Due Now + Pending</div>
      <div class="text-3xl font-bold mt-1 text-rose-400">$${(dueNow+pending).toFixed(2)}</div>
      <div class="text-xs text-muted mt-2">Cần đòi / chờ duyệt</div>
    </div>
  `;
}

function renderPlatformGrid(summary) {
  const html = summary.map(s => {
    if (s.status === "active" || s.total > 0) {
      return `
        <a href="#/platform/${s.key}" class="card-glow block rounded-2xl p-6 bg-gradient-to-br ${s.gradient} text-white">
          <div class="flex items-start justify-between mb-4">
            <div>
              <div class="text-xl font-bold flex items-center gap-2">${s.icon} ${s.name}</div>
              <div class="text-xs opacity-80 mt-1">${s.total} dashboard · ${s.success} ok / ${s.fail} lỗi</div>
            </div>
            <div class="text-right">
              <div class="text-2xl font-bold">$${s.total_unpaid.toFixed(0)}</div>
              <div class="text-xs opacity-80">unpaid</div>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-2 text-center text-sm bg-black/20 rounded-xl p-3">
            <div><div class="font-semibold">${s.total_clicks.toLocaleString()}</div><div class="text-xs opacity-70">clicks</div></div>
            <div><div class="font-semibold">$${s.total_due_now.toFixed(0)}</div><div class="text-xs opacity-70">due now</div></div>
            <div><div class="font-semibold">$${s.total_pending.toFixed(0)}</div><div class="text-xs opacity-70">pending</div></div>
          </div>
        </a>
      `;
    } else {
      return `
        <div class="rounded-2xl p-6 bg-slate-900 border border-slate-800 text-slate-500">
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="text-xl font-bold flex items-center gap-2">${s.icon} ${s.name}</div>
              <div class="text-xs mt-1">Adapter chưa có</div>
            </div>
            <span class="text-xs bg-slate-800 px-2 py-1 rounded">Coming soon</span>
          </div>
        </div>
      `;
    }
  }).join("");
  document.getElementById("platform-grid").innerHTML = html;
}

function renderPlatformDetail(platformKey, rows) {
  const meta = PLATFORM_META[platformKey] || { name: platformKey, gradient: "from-gray-500 to-gray-700", icon: "❓" };
  const isFP = platformKey === "firstpromoter";

  document.getElementById("platform-header").className = `rounded-2xl p-6 mb-6 bg-gradient-to-br ${meta.gradient} text-white`;
  document.getElementById("platform-header").innerHTML = `
    <a href="#/" class="text-xs opacity-80 hover:underline">← Back</a>
    <div class="flex items-end justify-between mt-2">
      <div>
        <div class="text-2xl font-bold flex items-center gap-2">${meta.icon} ${meta.name} Dashboard</div>
        <div class="text-sm opacity-80 mt-1">${rows.length} dashboards · ${CURRENT_DATE}</div>
      </div>
      <input id="filter-input" type="text" placeholder="🔍 Filter…"
             class="bg-black/30 placeholder-white/50 px-3 py-2 rounded-lg text-sm w-64 outline-none border border-white/20">
    </div>
  `;

  document.getElementById("table-head").innerHTML = `
    <tr>
      <th>Label</th><th>Owner</th><th>Email</th>
      <th class="text-right">${isFP ? "Clicks" : "Visitors"}</th>
      <th class="text-right">${isFP ? "Refs" : "Leads"}</th>
      <th class="text-right">${isFP ? "Customers" : "Conv."}</th>
      <th class="text-right">Unpaid</th>
      <th class="text-right">Paid</th>
      <th class="text-right">Due Now</th>
      ${isFP ? '<th class="text-right">Pending</th>' : ''}
      <th>Status</th>
      <th>Link</th>
    </tr>
  `;

  const body = rows.map(r => `
    <tr data-search="${(r.label||'')} ${(r.email||'')} ${(r.owner||'')}">
      <td><span class="font-medium">${r.label||''}</span></td>
      <td><span class="text-xs bg-slate-800 px-2 py-0.5 rounded">${r.owner||'-'}</span></td>
      <td class="text-xs text-muted">${r.email||'-'}</td>
      <td class="text-right">${r.clicks!=null ? Number(r.clicks).toLocaleString() : '-'}</td>
      <td class="text-right">${r.ref_count!=null ? r.ref_count : '-'}</td>
      <td class="text-right">${r.orders!=null ? r.orders : '-'}</td>
      <td class="text-right">${r.unpaid ? '$'+Number(r.unpaid).toFixed(2) : '-'}</td>
      <td class="text-right">${r.paid ? '$'+Number(r.paid).toFixed(2) : '-'}</td>
      <td class="text-right">${r.due_now && Number(r.due_now)>0 ? `<span class="due-now">$${Number(r.due_now).toFixed(2)}</span>` : '-'}</td>
      ${isFP ? `<td class="text-right">${r.pending_count ? r.pending_count + ' = $' + (Number(r.pending_amount)||0).toFixed(2) : '-'}</td>` : ''}
      <td>${r.error ? `<span class="err" title="${(r.error+'').replace(/"/g,'&quot;')}">${(r.error+'').substring(0,30)}${(r.error+'').length>30?'…':''}</span>` : '<span class="text-emerald-400">✓ OK</span>'}</td>
      <td>${r.ref_link ? `<a href="${r.ref_link}" target="_blank" class="text-blue-400 hover:underline text-xs">ref</a>` : ''}</td>
    </tr>
  `).join("");
  document.getElementById("table-body").innerHTML = body || `<tr><td colspan="12" class="text-center py-8 text-muted">Chưa có data</td></tr>`;

  document.getElementById("filter-input").addEventListener("input", e => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll("#table-body tr").forEach(tr => {
      tr.style.display = (tr.dataset.search||"").toLowerCase().includes(q) ? "" : "none";
    });
  });
}

// ============ ROUTING ============
async function route() {
  const hash = location.hash.slice(1) || "/";
  document.getElementById("loading").classList.remove("hidden");
  try {
    const data = await loadData(CURRENT_DATE);
    if (hash === "/" || hash === "") {
      document.getElementById("index-view").classList.remove("hidden");
      document.getElementById("platform-view").classList.add("hidden");
      const summary = computeSummary(data);
      renderKPI(summary);
      renderPlatformGrid(summary);
    } else if (hash.startsWith("/platform/")) {
      const platformKey = hash.replace("/platform/", "");
      document.getElementById("index-view").classList.add("hidden");
      document.getElementById("platform-view").classList.remove("hidden");
      renderPlatformDetail(platformKey, (data && data[platformKey]) || []);
    }
  } catch (e) {
    alert("Lỗi: " + e.message);
  } finally {
    document.getElementById("loading").classList.add("hidden");
  }
}

// ============ INIT ============
async function showApp() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  document.getElementById("login-user-display").textContent = USERNAME;

  // Load dates
  const dates = await loadDates();
  if (!dates.length) { alert("Chưa có data"); return; }
  CURRENT_DATE = dates[0];

  const picker = document.getElementById("date-picker");
  picker.innerHTML = dates.map(d => `<option value="${d}" ${d===CURRENT_DATE?'selected':''}>${d}</option>`).join("");
  picker.addEventListener("change", e => { CURRENT_DATE = e.target.value; CACHE = {}; route(); });

  document.getElementById("logout").addEventListener("click", logout);
  window.addEventListener("hashchange", route);
  await route();
}

document.getElementById("login-form").addEventListener("submit", async e => {
  e.preventDefault();
  const u = document.getElementById("login-user").value;
  const p = document.getElementById("login-pass").value;
  document.getElementById("login-error").textContent = "Đang login…";
  const ok = await login(u, p);
  if (ok) {
    document.getElementById("login-error").textContent = "";
    showApp();
  } else {
    document.getElementById("login-error").textContent = "Sai user / pass";
  }
});

if (TOKEN && USERNAME) showApp();
