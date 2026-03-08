/**
 * あるけみすと 自動探索 - メインスクリプト
 */

const SYNC_INTERVAL_MS = 5000;
const TIMER_INTERVAL_MS = 1000;
const MAX_DISPLAY_DROPS = 80;
const RANK_ORDER = ["S", "A", "B", "C", "D", "E", "F", "?"];

const $ = (e) => document.querySelector(e);
const $$ = (e) => document.querySelectorAll(e);

const st = $("#status");
const sb = $("#startBtn");
const sp = $("#stopBtn");
const tb = $("#themeBtn");
const statLevel = $("#statLevel");
const statLoop = $("#statLoop");
const statTime = $("#statTime");
const statDrops = $("#statDrops");
const lastMsg = $("#lastMessage");
const lastMsgText = $("#lastMsgText");
const lastMsgDrops = $("#lastMsgDrops");
const noResult = $("#noResult");
const dropRanks = $("#dropRanks");
const dropFilter = $("#dropFilter");
const dropsList = $("#dropsList");
const sortDropsBtn = $("#sortDropsBtn");
const activityLog = $("#activityLog");
const statsSummary = $("#statsSummary");
const stopReasonEl = $("#stopReason");
const off = $("#offlineMsg");

let clientStartMs = null;
let timerId = null;
let goPending = false;
let dropsSortOrder = "default";
let lastState = {};
let prevLoopCount = 0;

// --- テーマ ---
function initTheme() {
  const saved = localStorage.theme;
  const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  if (saved === "light" || (!saved && prefersLight)) {
    document.documentElement.setAttribute("data-theme", "light");
    tb.textContent = "☀️";
  }
}

function toggleTheme() {
  const d = document.documentElement;
  if (d.dataset.theme) {
    d.removeAttribute("data-theme");
    tb.textContent = "🌙";
    localStorage.theme = "";
  } else {
    d.dataset.theme = "light";
    tb.textContent = "☀️";
    localStorage.theme = "light";
  }
}

// --- タブ ---
function switchTab(tabId) {
  $$(".tab").forEach((t) => {
    const isActive = t.dataset.tab === tabId;
    t.classList.toggle("active", isActive);
    t.setAttribute("aria-selected", isActive);
  });
  $$(".tab-panel").forEach((p) => {
    const isActive = p.id === "tab-" + tabId;
    p.classList.toggle("active", isActive);
    p.hidden = !isActive;
  });
}

function setupTabs() {
  $$(".tab").forEach((t) => {
    t.addEventListener("click", () => switchTab(t.dataset.tab));
  });
}

// --- ユーティリティ ---
function fmtElapsed(ms) {
  if (ms == null || ms < 0) return "--:--";
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return h + "時間" + String(m % 60).padStart(2, "0") + "分";
  return String(m).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

function escapeHtml(s) {
  if (typeof s !== "string") return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function rankClass(s) {
  const m = s.match(/^\[([A-Za-z?])\]/);
  return m ? m[1].toUpperCase() : "?";
}

function renderDropTag(d) {
  const c = rankClass(d);
  return '<span class="' + escapeHtml(c) + '">' + escapeHtml(d) + "</span>";
}

function sortDropsByRank(drops, order) {
  if (order === "default") return drops;
  const getRankIdx = (d) => RANK_ORDER.indexOf(rankClass(d));
  return [...drops].sort((a, b) => {
    const ia = getRankIdx(a);
    const ib = getRankIdx(b);
    if (order === "rank-asc") return ia - ib;
    return ib - ia;
  });
}

function filterDropsByRank(drops, rank) {
  if (!rank) return drops;
  return drops.filter((d) => rankClass(d) === rank);
}

// --- 周回数アニメーション ---
function updateLoopWithAnimation(count) {
  if (!statLoop) return;
  const n = Number(count) || 0;
  if (n > prevLoopCount) {
    statLoop.classList.add("updated");
    setTimeout(() => statLoop.classList.remove("updated"), 350);
  }
  prevLoopCount = n;
  statLoop.textContent = n;
}

// --- 統計サマリ ---
function updateStatsSummary(d) {
  if (!statsSummary) return;
  const loop = d.loop_count || 0;
  const drops = (d.drops || []).length;
  statsSummary.innerHTML =
    "<p>総周回: <strong>" +
    escapeHtml(String(loop)) +
    "</strong></p>" +
    "<p>総ドロップ数: <strong>" +
    escapeHtml(String(drops)) +
    "</strong></p>";
}

// --- UI 更新 ---
function setUIFromState(d) {
  lastState = d;
  const run = d.running;
  const lucky = d.lucky;
  st.setAttribute("aria-busy", run || lucky ? "true" : "false");

  if (d.stop_reason) {
    stopReasonEl.style.display = "block";
    stopReasonEl.textContent = "⚠ " + escapeHtml(d.stop_reason);
    stopReasonEl.style.color = "var(--danger)";
  } else {
    stopReasonEl.style.display = "none";
  }

  const waitSec = d.lucky_chance_wait_sec || 20;
  if (lucky) {
    st.textContent =
      "★ 一時停止（ラッキーチャンス） 「再開」で" + waitSec + "秒後に開始";
    st.className = "status lucky";
    sb.disabled = false;
    sb.textContent = "▶ 再開";
    sp.disabled = false;
  } else if (run) {
    st.textContent = "探索実行中";
    st.className = "status running";
    sb.disabled = true;
    sb.textContent = "▶ 自動探索開始";
    sp.disabled = false;
  } else {
    st.textContent = "停止済み - 「開始」で再開";
    st.className = "status ready";
    sb.disabled = false;
    sp.disabled = true;
    sp.setAttribute("disabled", "");
  }

  const level = d.level != null ? d.level : 0;
  if (statLevel) {
    statLevel.textContent = level > 0 ? level : "-";
    statLevel.classList.toggle("level-max", level >= 100);
  }

  updateLoopWithAnimation(d.loop_count || 0);
  if (statDrops) statDrops.textContent = (d.drops || []).length;

  if (!run && !goPending) {
    clientStartMs = null;
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  } else if (run) {
    goPending = false;
    if (clientStartMs == null && d.session_started_at) {
      clientStartMs = new Date(d.session_started_at).getTime();
    }
  }
  if (timerId) clearInterval(timerId);
  if (clientStartMs != null) {
    timerId = setInterval(() => {
      if (statTime) statTime.textContent = fmtElapsed(Date.now() - clientStartMs);
    }, TIMER_INTERVAL_MS);
  }
  if (statTime) {
    statTime.textContent = fmtElapsed(
      clientStartMs != null ? Date.now() - clientStartMs : null
    );
  }

  // ドロップランク集計（sort ボタンはもう HTML にあるので追加しない）
  const byRank = d.drops_by_rank || {};
  const rankKeys = Object.keys(byRank).sort(
    (a, b) => RANK_ORDER.indexOf(a) - RANK_ORDER.indexOf(b)
  );
  if (dropRanks) {
    dropRanks.innerHTML =
      rankKeys.length
        ? rankKeys
            .map(
              (r) =>
                '<span class="' +
                escapeHtml(r) +
                '">' +
                escapeHtml(r) +
                ": " +
                byRank[r] +
                "</span>"
            )
            .join("")
        : '<span class="C">まだなし</span>';
  }

  // ドロップリスト（フィルタ・ソート適用）
  const rawDrops = d.drops || [];
  const filterRank = dropFilter ? dropFilter.value : "";
  const filtered = filterDropsByRank(rawDrops, filterRank);
  const sortedDrops = sortDropsByRank(filtered, dropsSortOrder);
  if (dropsList) {
    dropsList.innerHTML =
      sortedDrops.slice(-MAX_DISPLAY_DROPS).map(renderDropTag).join("") || "";
  }

  // 直近結果
  const acts = d.activity_log || [];
  const lastAct = acts[0];
  if (d.last_message && lastAct) {
    noResult.style.display = "none";
    lastMsg.style.display = "flex";
    const loopEl = $("#loopCount");
    if (loopEl) loopEl.textContent = "#" + lastAct.loop + "周目";
    lastMsgText.textContent = d.last_message;
    lastMsgDrops.innerHTML = (lastAct.drops || []).map(renderDropTag).join("");
  } else if (d.last_message) {
    noResult.style.display = "none";
    lastMsg.style.display = "flex";
    const loopEl = $("#loopCount");
    if (loopEl) loopEl.textContent = "";
    lastMsgText.textContent = d.last_message;
    lastMsgDrops.innerHTML = "";
  } else {
    noResult.style.display = "block";
    lastMsg.style.display = "none";
  }

  // アクティビティログ
  if (activityLog) {
    activityLog.innerHTML =
      (d.activity_log || [])
        .slice(0, 15)
        .map(
          (a) =>
            '<div class="activity-item"><span class="loop">#' +
            escapeHtml(String(a.loop)) +
            "周目</span><span class=\"msg\">" +
            escapeHtml(a.msg || "") +
            '</span><div class="drops">' +
            (a.drops || []).map(renderDropTag).join("") +
            "</div></div>"
        )
        .join("") ||
      '<p style="color:var(--muted)">まだアクティビティがありません</p>';
  }

  updateStatsSummary(d);
}

async function syncState() {
  try {
    const r = await fetch("/api/state");
    if (r.ok) {
      const d = await r.json();
      setUIFromState(d);
      return true;
    }
    if (!navigator.onLine) return false;
    st.textContent = "同期失敗 (" + r.status + ") - 再接続を試行中";
    st.setAttribute("aria-busy", "false");
  } catch (e) {
    if (navigator.onLine) {
      st.textContent = "同期失敗 - 再接続を試行中";
      st.setAttribute("aria-busy", "false");
    }
  }
  return false;
}

function setupEventSource() {
  const es = new EventSource("/api/events");
  es.onopen = async () => {
    if (!(await syncState())) {
      st.textContent = "接続済み - 準備OK";
      st.className = "status ready";
      st.setAttribute("aria-busy", "false");
    }
  };
  es.onerror = () => {
    st.textContent = "再接続中...";
    st.className = "status";
    st.setAttribute("aria-busy", "true");
    syncState();
  };
  es.addEventListener("lucky_chance", (e) => {
    try {
      const d = JSON.parse(e.data || "{}");
      setUIFromState({ ...d, running: false, lucky: true });
      sb.disabled = false;
      sb.textContent = "▶ 再開";
      sp.disabled = true;
      if (Notification.permission === "granted") {
        new Notification("あるけみすと", { body: "ラッキーチャンス！" });
      }
    } catch (err) {
      console.error("lucky_chance parse error:", err);
    }
  });
  es.addEventListener("exploration_started", (e) => {
    try {
      const d = JSON.parse(e.data || "{}");
      setUIFromState({ ...d, running: true, lucky: false });
      sb.disabled = true;
      sp.disabled = false;
    } catch (err) {
      console.error("exploration_started parse error:", err);
    }
  });
  es.addEventListener("exploration_stopped", (e) => {
    goPending = false;
    try {
      const d = JSON.parse(e.data || "{}");
      setUIFromState({ ...d, running: false, lucky: false });
      sb.disabled = false;
      sp.disabled = true;
    } catch (err) {
      console.error("exploration_stopped parse error:", err);
    }
  });
  es.addEventListener("exploration_log", (e) => {
    try {
      setUIFromState(JSON.parse(e.data || "{}"));
    } catch (err) {
      console.error("exploration_log parse error:", err);
    }
  });
}

function setupStartBtn() {
  sb.addEventListener("click", async () => {
    if (sb.disabled) return;
    sb.disabled = true;
    goPending = true;
    clientStartMs = Date.now();
    sp.disabled = false;
    if (timerId) clearInterval(timerId);
    timerId = setInterval(() => {
      if (statTime) statTime.textContent = fmtElapsed(Date.now() - clientStartMs);
    }, TIMER_INTERVAL_MS);
    if (statTime) statTime.textContent = fmtElapsed(0);
    try {
      const r = await fetch("/api/go", { method: "POST" });
      if (r.ok) {
        st.textContent = "送信完了 - 探索開始を待機中";
      } else {
        throw new Error("HTTP " + r.status);
      }
    } catch (e) {
      sb.disabled = false;
      goPending = false;
      clientStartMs = null;
      if (timerId) {
        clearInterval(timerId);
        timerId = null;
      }
      st.textContent = "接続エラー - サーバーを確認してください";
      st.setAttribute("aria-busy", "false");
    }
  });
}

function setupStopBtn() {
  sp.addEventListener("click", async () => {
    if (sp.disabled) return;
    try {
      const r = await fetch("/api/stop-exploration", { method: "POST" });
      if (r.ok) {
        st.textContent = "停止予約 - このループ終了後に停止します";
      } else {
        throw new Error("HTTP " + r.status);
      }
    } catch (e) {
      st.textContent = "接続エラー - 停止できませんでした";
      st.setAttribute("aria-busy", "false");
    }
  });
}

// ドロップソート・フィルタ
function setupDropControls() {
  if (sortDropsBtn) {
    sortDropsBtn.addEventListener("click", () => {
      dropsSortOrder =
        dropsSortOrder === "default"
          ? "rank-desc"
          : dropsSortOrder === "rank-desc"
            ? "rank-asc"
            : "default";
      setUIFromState(lastState);
    });
  }
  if (dropFilter) {
    dropFilter.addEventListener("change", () => setUIFromState(lastState));
  }
}

// キーボード
function setupKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.repeat) {
      if (sb && !sb.disabled) sb.click();
    }
    if (e.key === "Escape" && !e.repeat) {
      if (sp && !sp.disabled) sp.click();
    }
    if (e.key === "t" || e.key === "T") {
      if (e.ctrlKey || e.metaKey) return;
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") return;
      toggleTheme();
    }
  });
}

// 初期化
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  tb.addEventListener("click", toggleTheme);
  setupTabs();
  switchTab("dashboard");
  setupDropControls();
  setupKeyboard();

  window.addEventListener("online", () => {
    off.style.display = "none";
  });
  window.addEventListener("offline", () => {
    off.style.display = "block";
    st.textContent = "オフライン";
    st.setAttribute("aria-busy", "false");
  });
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }

  syncState();
  setInterval(syncState, SYNC_INTERVAL_MS);
  setupEventSource();
  setupStartBtn();
  setupStopBtn();
});
