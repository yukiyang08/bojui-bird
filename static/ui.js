/* ==== 不揪鳥 · 共用前端 UI ====
   liff.html / preview.html 各自提供:  state, app, apiCall(), reloadData()
   這支檔案負責畫面、彈窗、動畫、彩帶。 */

const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const ICON = {
  target: "lucide:utensils-crossed",
  chev: "lucide:chevron-right",
};

const TAGLINES = [
  "放鳥一時爽，排行榜火葬場",
  "不揪不揪不揪",
  "今天，你行善了嗎？",
  "揪團的是英雄，放鳥的是鳥",
];

/* ---------- helpers ---------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function hashHue(s) {
  let h = 0;
  for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 360;
}
function birdSvg(hue) {
  return (
    `<svg viewBox="0 0 40 40" aria-hidden="true">` +
    `<ellipse cx="20" cy="23" rx="13" ry="12" fill="hsl(${hue} 66% 62%)"/>` +
    `<path d="M20 8c4 0 6 3 6 5 0 1.4-2.7 1.6-6 1.6s-6-.2-6-1.6c0-2 2-5 6-5z" fill="hsl(${hue} 70% 74%)"/>` +
    `<ellipse cx="20" cy="26" rx="7.5" ry="6.5" fill="hsl(${hue} 58% 84%)"/>` +
    `<circle cx="15.6" cy="20" r="2.9" fill="#fff"/><circle cx="16.5" cy="20.4" r="1.4" fill="#241f18"/>` +
    `<circle cx="24.4" cy="20" r="2.9" fill="#fff"/><circle cx="25.3" cy="20.4" r="1.4" fill="#241f18"/>` +
    `<path d="M20 22.6l2.8 2.1h-5.6z" fill="hsl(32 90% 52%)"/>` +
    `<path d="M7.5 22.2c-2 0-4 1.1-5 2.7 1.8 1.4 3.7 1.7 5.5.7z" fill="hsl(${hue} 60% 50%)"/>` +
    `</svg>`
  );
}
function fmtMoney(n) {
  const s = "$" + Math.abs(n).toLocaleString();
  return n < 0 ? "退 " + s : s;
}
function fmtDate(s) {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d) ? "" : `${d.getMonth() + 1}/${d.getDate()}`;
}
function buzz(pattern) {
  try { navigator.vibrate && navigator.vibrate(pattern); } catch (e) {}
}

/* 若頁面是在 LINE App 內、從聊天室開啟的，就把一則通知發回該聊天室。
   在瀏覽器 / 沒有 chat_message.write 權限時靜默略過。 */
async function notifyChat(text) {
  try {
    if (window.liff && liff.isInClient && liff.isInClient()) {
      await liff.sendMessages([{ type: "text", text }]);
    }
  } catch (e) {
    /* ignore */
  }
}

function reasonTag(s) {
  const r = (s || "").trim();
  return r ? `（${r}）` : "";
}

/* ---------- chrome ---------- */

function initChrome() {
  const m = document.querySelector(".mascot");
  if (m) m.innerHTML = `<img src="images/logo.png" alt="不揪鳥" width="40" height="40">`;
  const say = document.getElementById("say");
  if (say) say.textContent = TAGLINES[Math.floor(Math.random() * TAGLINES.length)];
}

function showState(icon, text) {
  app.innerHTML = `<p class="state"><iconify-icon icon="${icon}"></iconify-icon>${escapeHtml(text)}</p>`;
}

function wireClicks() {
  document.addEventListener("click", (ev) => {
    const bird = ev.target.closest(".pod-bird");
    if (bird) {
      buzz(8);
      if (!REDUCE) {
        const r = bird.getBoundingClientRect();
        burst(r.left + r.width / 2, r.top + r.height / 2, 36);
      }
      return;
    }
    const row = ev.target.closest("[data-kind]");
    if (row) return openEditSheet(row.dataset.kind, row.dataset.id);
    const act = ev.target.closest("[data-act]");
    if (act && act.dataset.act === "target") return openTargetSheet();
    if (act && act.dataset.act === "add") return openAddSheet();
  });
}

/* ---------- render ---------- */

function render(data) {
  state.data = data;
  const ranking = data.ranking || [];
  app.innerHTML =
    podiumBlock(ranking) +
    section("大餐基金", "lucide:piggy-bank", targetGroup(data.dinner_target)) +
    section(
      data.dinner_target ? "戰績排行 · 餐費試算" : "戰績排行",
      "lucide:list-ordered",
      rankingGroup(ranking)
    ) +
    section("功德榜", "lucide:heart-handshake", logGroup("merit", data.merit_log || [], "還沒有人做好事，鳥。")) +
    section("罪人榜", "lucide:gavel", logGroup("sin", data.sin_log || [], "目前無人放鳥，讚。")) +
    `<p class="foot">點任一筆紀錄可改／刪 · 右上角「記一筆」手動加</p>`;

  animateNumbers();
  if (!state._welcomed && ranking.length && !REDUCE) {
    state._welcomed = true;
    setTimeout(burstFromTop, 350);
  }
}

function section(label, icon, groupHtml) {
  const ic = icon ? `<iconify-icon icon="${icon}"></iconify-icon>` : "";
  return `<p class="label">${ic}${label}</p><div class="group">${groupHtml}</div>`;
}

function podiumBlock(ranking) {
  if (!ranking.length) {
    return `<div class="podium empty">${birdSvg(42)}<p>還沒有戰績<br>快去記第一筆</p></div>`;
  }
  const top = ranking.slice(0, 3);
  const order = top.length === 3 ? [1, 0, 2] : top.length === 2 ? [1, 0] : [0];
  const medals = ["🥇", "🥈", "🥉"];
  const cells = order
    .map((idx) => {
      const m = top[idx];
      const p = m.total_points;
      const cls = p > 0 ? "pos" : p < 0 ? "neg" : "zero";
      return (
        `<div class="pod pod${idx + 1}">` +
        `<div class="pod-bird">${birdSvg(hashHue(m.display_name))}<span class="medal">${medals[idx]}</span></div>` +
        `<div class="pod-name">${escapeHtml(m.display_name)}</div>` +
        `<div class="pod-step">` +
        `<span class="pod-pts ${cls}" data-count="${p}">0</span>` +
        `<span class="pod-rank">${idx + 1}</span>` +
        `</div></div>`
      );
    })
    .join("");
  return `<div class="podium">${cells}</div>`;
}

function targetGroup(amount) {
  const val = amount
    ? `<span class="val strong">$${Number(amount).toLocaleString()}</span>`
    : `<span class="val">未設定</span>`;
  return (
    `<button class="line" data-act="target">` +
    `<iconify-icon class="ico" icon="lucide:piggy-bank"></iconify-icon>` +
    `<span class="main"><div class="name">大餐目標金額</div></span>` +
    val +
    `<iconify-icon class="chev" icon="${ICON.chev}"></iconify-icon>` +
    `</button>`
  );
}

/* 記住上次名次，畫 ▲/▼；每次載入只快照一次 */
let _rankBaseline = null;
function rankMovement(members) {
  const key = "bird_rank_" + (state.groupId || "x");
  if (_rankBaseline === null) {
    try { _rankBaseline = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { _rankBaseline = {}; }
  }
  const cur = {};
  members.forEach((m, i) => (cur[m.display_name] = i));
  try { localStorage.setItem(key, JSON.stringify(cur)); } catch (e) {}
  return (name) => (name in _rankBaseline ? _rankBaseline[name] - cur[name] : null);
}

function rankingGroup(members) {
  if (!members.length) return `<p class="row-empty">還沒有人被記點</p>`;
  const scale = Math.max(5, ...members.map((m) => Math.abs(m.total_points)));
  const move = rankMovement(members);
  return members
    .map((m, i) => {
      const p = m.total_points;
      const cls = p > 0 ? "pos" : p < 0 ? "neg" : "zero";
      const w = Math.round(Math.min(1, Math.abs(p) / scale) * 50);
      const side = p < 0 ? "right" : "left";
      const bar = `<div class="bar"><i class="${cls}" style="width:${w}%;${side}:50%"></i></div>`;
      const money = m.pay == null ? "" : `<span class="money${m.pay < 0 ? " back" : ""}">${fmtMoney(m.pay)}</span>`;
      const d = move(m.display_name);
      const chip =
        d == null ? "" : d > 0 ? `<span class="chip up">▲${d}</span>` : d < 0 ? `<span class="chip down">▼${-d}</span>` : `<span class="chip flat">–</span>`;
      return (
        `<div class="line rk${i === 0 ? " first" : ""}">` +
        `<span class="rank">${i + 1}</span>` +
        `<span class="main"><div class="name">${escapeHtml(m.display_name)}${chip}</div>${bar}</span>` +
        `<span class="trail"><span class="pts big ${cls}" data-count="${p}">0</span>${money}</span>` +
        `</div>`
      );
    })
    .join("");
}

function logGroup(kind, entries, emptyText) {
  if (!entries.length) return `<p class="row-empty">${escapeHtml(emptyText)}</p>`;
  return entries
    .map((e) => {
      const cls = e.delta > 0 ? "pos" : "neg";
      const sub = e.reason ? `<div class="sub">${escapeHtml(e.reason)}</div>` : "";
      return (
        `<button class="line log ${cls}" data-kind="${kind}" data-id="${escapeHtml(e.id)}">` +
        `<span class="av">${birdSvg(hashHue(e.display_name))}</span>` +
        `<span class="main"><div class="name">${escapeHtml(e.display_name)}</div>${sub}</span>` +
        `<span class="trail"><span class="pts ${cls}">${e.delta > 0 ? "+" : ""}${e.delta}</span>` +
        `<span class="meta">${fmtDate(e.created_at)}</span></span>` +
        `<iconify-icon class="chev" icon="${ICON.chev}"></iconify-icon>` +
        `</button>`
      );
    })
    .join("");
}

/* ---------- number count-up ---------- */

function animateNumbers() {
  document.querySelectorAll("[data-count]").forEach((el) => {
    const to = Number(el.dataset.count);
    if (REDUCE) {
      el.textContent = (to > 0 ? "+" : "") + to;
      return;
    }
    const t0 = performance.now();
    const dur = 650;
    (function frame(t) {
      const k = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      const v = Math.round(to * e);
      el.textContent = (v > 0 ? "+" : "") + v;
      if (k < 1) requestAnimationFrame(frame);
      else el.textContent = (to > 0 ? "+" : "") + to;
    })(t0);
  });
}

/* ---------- confetti ---------- */

let _fx = null;
let _fxCtx = null;
let _parts = [];
let _raf = 0;
const FX_COLORS = ["#ff7a1a", "#ffd43b", "#1f9d55", "#4dabf7", "#e64980"];

function fxInit() {
  _fx = document.createElement("canvas");
  _fx.id = "fx";
  document.body.appendChild(_fx);
  _fxCtx = _fx.getContext("2d");
  const resize = () => {
    const dpr = window.devicePixelRatio || 1;
    _fx.width = innerWidth * dpr;
    _fx.height = innerHeight * dpr;
    _fx.style.width = innerWidth + "px";
    _fx.style.height = innerHeight + "px";
    _fxCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  window.addEventListener("resize", resize);
}

function burst(x, y, n) {
  if (REDUCE) return;
  if (!_fx) fxInit();
  n = n || 90;
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    const sp = 2 + Math.random() * 6;
    _parts.push({
      x, y,
      vx: Math.cos(a) * sp,
      vy: Math.sin(a) * sp - 3,
      g: 0.12 + Math.random() * 0.1,
      s: 4 + Math.random() * 5,
      rot: Math.random() * 6,
      vr: (Math.random() - 0.5) * 0.4,
      c: FX_COLORS[i % FX_COLORS.length],
      life: 55 + Math.random() * 35,
      t: 0,
    });
  }
  if (!_raf) _raf = requestAnimationFrame(fxTick);
}

function fxTick() {
  _fxCtx.clearRect(0, 0, innerWidth, innerHeight);
  _parts = _parts.filter((p) => p.t < p.life);
  for (const p of _parts) {
    p.t++;
    p.vy += p.g;
    p.vx *= 0.99;
    p.x += p.vx;
    p.y += p.vy;
    p.rot += p.vr;
    _fxCtx.save();
    _fxCtx.translate(p.x, p.y);
    _fxCtx.rotate(p.rot);
    _fxCtx.globalAlpha = Math.max(0, 1 - p.t / p.life);
    _fxCtx.fillStyle = p.c;
    _fxCtx.fillRect(-p.s / 2, -p.s / 2, p.s, p.s * 0.6);
    _fxCtx.restore();
  }
  _raf = _parts.length ? requestAnimationFrame(fxTick) : 0;
}

function burstFromTop() {
  const el = document.querySelector(".pod1 .pod-bird") || document.querySelector(".podium");
  if (!el) return;
  const r = el.getBoundingClientRect();
  burst(r.left + r.width / 2, r.top + r.height / 2, 110);
}

function shake() {
  document.body.classList.add("shake");
  setTimeout(() => document.body.classList.remove("shake"), 450);
}

function celebrate(delta) {
  if (delta > 0) {
    buzz(15);
    burst(window.innerWidth / 2, 130, 90);
  } else {
    buzz([8, 40, 8]);
    if (!REDUCE) shake();
  }
}

/* ---------- sheets ---------- */

function mountSheet(html) {
  const el = document.createElement("div");
  el.className = "backdrop";
  el.innerHTML = `<div class="sheet" role="dialog" aria-modal="true">${html}</div>`;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  const close = () => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 240);
  };
  el.addEventListener("click", (ev) => {
    if (ev.target === el) close();
  });
  return { el, close };
}

function wireStep(el, initial) {
  let v = initial;
  const vEl = el.querySelector(".v");
  const paint = () => {
    vEl.textContent = (v > 0 ? "+" : "") + v;
    vEl.className = "v " + (v > 0 ? "pos" : "neg");
  };
  el.querySelectorAll("[data-step]").forEach((b) =>
    b.addEventListener("click", () => {
      const s = Number(b.dataset.step);
      v += s;
      if (v === 0) v += s;
      v = Math.max(-99, Math.min(99, v));
      buzz(6);
      paint();
    })
  );
  paint();
  return () => v;
}

const STEP_HTML =
  `<div class="step">` +
  `<button type="button" data-step="-1"><iconify-icon icon="lucide:minus"></iconify-icon></button>` +
  `<span class="v"></span>` +
  `<button type="button" data-step="1"><iconify-icon icon="lucide:plus"></iconify-icon></button>` +
  `</div>`;

const setBusy = (el, on) => el.querySelectorAll("button").forEach((b) => (b.disabled = on));

function openEditSheet(kind, id) {
  const list = kind === "merit" ? state.data.merit_log : state.data.sin_log;
  const rec = (list || []).find((e) => String(e.id) === id);
  if (!rec) return;

  const { el, close } = mountSheet(
    `<h3><iconify-icon icon="lucide:pencil"></iconify-icon>編輯紀錄 · ${escapeHtml(rec.display_name)}</h3>
     <div class="fld"><span>點數</span>${STEP_HTML}</div>
     <div class="fld"><span>事蹟</span><input type="text" class="reason" maxlength="60" placeholder="原因"></div>
     <div class="acts">
       <button class="btn ghost" type="button" data-del><iconify-icon icon="lucide:trash-2"></iconify-icon>刪除</button>
       <button class="btn primary" type="button" data-save>儲存</button>
     </div>
     <p class="err"></p>`
  );
  const getDelta = wireStep(el, rec.delta);
  const reason = el.querySelector(".reason");
  const err = el.querySelector(".err");
  reason.value = rec.reason || "";

  el.querySelector("[data-save]").addEventListener("click", async () => {
    setBusy(el, true);
    err.textContent = "";
    try {
      const delta = getDelta();
      const res = await apiCall("PATCH", `/api/records/${rec.id}`, { delta, reason: reason.value });
      close();
      await reloadData();
      celebrate(delta);
      const total = res && res.total_points != null ? ` · 目前 ${res.total_points} 點` : "";
      notifyChat(`✏️ 改了 ${rec.display_name} 的紀錄：${delta > 0 ? "+" : ""}${delta}${reasonTag(reason.value)}${total}`);
    } catch (e) {
      err.textContent = e.message;
      setBusy(el, false);
    }
  });
  el.querySelector("[data-del]").addEventListener("click", async () => {
    if (!confirm("刪除這筆紀錄？")) return;
    setBusy(el, true);
    err.textContent = "";
    try {
      await apiCall("DELETE", `/api/records/${rec.id}`);
      buzz(30);
      close();
      await reloadData();
      notifyChat(`🗑️ 刪掉 ${rec.display_name} 的一筆紀錄（原 ${rec.delta > 0 ? "+" : ""}${rec.delta}）`);
    } catch (e) {
      err.textContent = e.message;
      setBusy(el, false);
    }
  });
}

function openAddSheet() {
  const members = state.data.members || [];
  if (!members.length) return alert("還沒有任何成員可以記點");
  const opts = members
    .map((m) => `<option value="${escapeHtml(m.line_user_id)}">${escapeHtml(m.display_name)}</option>`)
    .join("");

  const { el, close } = mountSheet(
    `<h3><iconify-icon icon="lucide:feather"></iconify-icon>手動記一筆</h3>
     <div class="fld"><span>對象（限名單上的人）</span><select class="member">${opts}</select></div>
     <div class="fld"><span>點數</span>${STEP_HTML}</div>
     <div class="fld"><span>事蹟</span><input type="text" class="reason" maxlength="60" placeholder="原因"></div>
     <div class="acts"><button class="btn primary" type="button" data-save>新增</button></div>
     <p class="err"></p>`
  );
  const getDelta = wireStep(el, 1);
  const member = el.querySelector(".member");
  const reason = el.querySelector(".reason");
  const err = el.querySelector(".err");

  el.querySelector("[data-save]").addEventListener("click", async () => {
    setBusy(el, true);
    err.textContent = "";
    try {
      const delta = getDelta();
      const name = member.options[member.selectedIndex].text;
      const res = await apiCall("POST", "/api/records", {
        line_group_id: state.groupId,
        target_user_id: member.value,
        delta,
        reason: reason.value,
      });
      close();
      await reloadData();
      celebrate(delta);
      const total = res && res.total_points != null ? ` · 目前 ${res.total_points} 點` : "";
      notifyChat(`📝 ${name} ${delta > 0 ? "+" : ""}${delta}${reasonTag(reason.value)}${total}（記於排行榜頁）`);
    } catch (e) {
      err.textContent = e.message;
      setBusy(el, false);
    }
  });
}

function openTargetSheet() {
  const cur = state.data.dinner_target;
  const { el, close } = mountSheet(
    `<h3><iconify-icon icon="${ICON.target}"></iconify-icon>大餐目標金額</h3>
     <div class="fld"><span>!算帳 不帶數字時就用這個金額</span>
       <input type="number" inputmode="numeric" class="amt" min="1" placeholder="例如 12000"></div>
     <div class="acts"><button class="btn primary" type="button" data-save>儲存</button></div>
     <p class="err"></p>`
  );
  const amt = el.querySelector(".amt");
  const err = el.querySelector(".err");
  if (cur) amt.value = cur;

  el.querySelector("[data-save]").addEventListener("click", async () => {
    const amount = parseInt(amt.value, 10);
    if (!amount || amount <= 0) {
      err.textContent = "請輸入大於 0 的金額";
      return;
    }
    setBusy(el, true);
    err.textContent = "";
    try {
      await apiCall("PUT", "/api/target", { line_group_id: state.groupId, amount });
      close();
      await reloadData();
      notifyChat(`🍜 大餐目標金額設為 $${amount.toLocaleString()}`);
    } catch (e) {
      err.textContent = e.message;
      setBusy(el, false);
    }
  });
}
