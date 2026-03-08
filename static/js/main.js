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
const statusText = st?.querySelector(".status-text");
const sb = $("#startBtn");
const sp = $("#stopBtn");
const tb = $("#themeBtn");
const helpBtn = $("#helpBtn");
const helpModal = $("#helpModal");
const helpClose = $("#helpClose");
const loadingOverlay = $("#loadingOverlay");
const reconnectToast = $("#reconnectToast");
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
const dropsEmpty = $("#dropsEmpty");
const sortDropsBtn = $("#sortDropsBtn");
const sortDropsLabel = $("#sortDropsLabel");
const activityLog = $("#activityLog");
const activityEmpty = $("#activityEmpty");
const activityScroll = $("#activityScroll");
const autoScrollToggle = $("#autoScrollToggle");
const statsLoop = $("#statsLoop");
const statsDrops = $("#statsDrops");
const lastSyncEl = $("#lastSync");
const stopReasonEl = $("#stopReason");
const off = $("#offlineMsg");

let clientStartMs = null;
let timerId = null;
let goPending = false;
let dropsSortOrder = "default";
let lastState = {};
let prevLoopCount = 0;
let lastSyncAt = null;
let wasOffline = false;
let luckySoundEnabled = localStorage.luckySound !== "0";

// ラッキーチャンス用ビープ音（Web Audio API）
function playLuckySound() {
  if (!luckySoundEnabled) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
  } catch (_) {}
}

function setStatusText(s) {
  if (statusText) statusText.textContent = s;
  else if (st) st.textContent = s;
}

// --- テーマ ---
function initTheme() {
  const saved = localStorage.theme;
  const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  if (saved === "light" || (!saved && prefersLight)) {
    document.documentElement.setAttribute("data-theme", "light");
    if (tb) tb.textContent = "☀️";
  }
}

function toggleTheme() {
  const d = document.documentElement;
  if (d.dataset.theme) {
    d.removeAttribute("data-theme");
    if (tb) tb.textContent = "🌙";
    localStorage.theme = "";
  } else {
    d.dataset.theme = "light";
    if (tb) tb.textContent = "☀️";
    localStorage.theme = "light";
  }
}

// --- ヘルプモーダル ---
function openHelp() {
  if (helpModal) {
    helpModal.hidden = false;
    helpClose?.focus();
  }
}

function closeHelp() {
  if (helpModal) helpModal.hidden = true;
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

function fmtLastSync(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return "たった今";
  if (sec < 3600) return Math.floor(sec / 60) + "分前";
  if (sec < 86400) return Math.floor(sec / 3600) + "時間前";
  return d.toLocaleDateString();
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

function getSortLabel() {
  if (dropsSortOrder === "default") return "並び替え: デフォルト";
  if (dropsSortOrder === "rank-desc") return "並び替え: ランク▼";
  return "並び替え: ランク▲";
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

// --- ローディング・トースト ---
function hideLoading() {
  if (loadingOverlay) loadingOverlay.style.display = "none";
}

function showReconnectToast() {
  if (!reconnectToast) return;
  reconnectToast.style.display = "block";
  setTimeout(() => {
    reconnectToast.style.display = "none";
  }, 2500);
}

// --- UI 更新 ---
function setUIFromState(d) {
  lastState = d;
  lastSyncAt = d.at || new Date().toISOString();
  const run = d.running;
  const lucky = d.lucky;
  if (st) st.setAttribute("aria-busy", run || lucky ? "true" : "false");

  if (d.stop_reason) {
    if (stopReasonEl) {
      stopReasonEl.style.display = "block";
      stopReasonEl.textContent = "⚠ " + escapeHtml(d.stop_reason);
      stopReasonEl.style.color = "var(--danger)";
    }
  } else {
    if (stopReasonEl) stopReasonEl.style.display = "none";
  }

  const waitSec = d.lucky_chance_wait_sec || 20;
  if (lucky) {
    setStatusText("★ 一時停止（ラッキーチャンス） 「再開」で" + waitSec + "秒後に開始");
    st?.classList.remove("ready", "running");
    st?.classList.add("lucky");
    if (sb) { sb.disabled = false; sb.textContent = "▶ 再開"; }
    if (sp) sp.disabled = false;
    playLuckySound();
  } else if (run) {
    setStatusText("探索実行中");
    st?.classList.remove("ready", "lucky");
    st?.classList.add("running");
    if (sb) { sb.disabled = true; sb.textContent = "▶ 自動探索開始"; }
    if (sp) sp.disabled = false;
  } else {
    setStatusText("停止済み - 「開始」で再開");
    st?.classList.remove("running", "lucky");
    st?.classList.add("ready");
    if (sb) sb.disabled = false;
    if (sp) { sp.disabled = true; sp.setAttribute("disabled", ""); }
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
    if (timerId) { clearInterval(timerId); timerId = null; }
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
    statTime.textContent = fmtElapsed(clientStartMs != null ? Date.now() - clientStartMs : null);
  }

  // ドロップランク集計
  const byRank = d.drops_by_rank || {};
  const rankKeys = Object.keys(byRank).sort(
    (a, b) => RANK_ORDER.indexOf(a) - RANK_ORDER.indexOf(b)
  );
  if (dropRanks) {
    dropRanks.innerHTML = rankKeys.length
      ? rankKeys.map((r) => '<span class="' + escapeHtml(r) + '">' + escapeHtml(r) + ": " + byRank[r] + "</span>").join("")
      : '<span class="C">まだなし</span>';
  }

  // ドロップリスト
  const rawDrops = d.drops || [];
  const filterRank = dropFilter ? dropFilter.value : "";
  const filtered = filterDropsByRank(rawDrops, filterRank);
  const sortedDrops = sortDropsByRank(filtered, dropsSortOrder);
  if (dropsList) {
    const html = sortedDrops.slice(-MAX_DISPLAY_DROPS).map(renderDropTag).join("");
    dropsList.innerHTML = html;
    dropsList.style.display = html ? "flex" : "none";
  }
  if (dropsEmpty) {
    dropsEmpty.style.display = sortedDrops.length === 0 ? "block" : "none";
  }

  if (sortDropsLabel) sortDropsLabel.textContent = getSortLabel();

  // 直近結果
  const acts = d.activity_log || [];
  const lastAct = acts[0];
  if (d.last_message && lastAct) {
    if (noResult) noResult.style.display = "none";
    if (lastMsg) lastMsg.style.display = "flex";
    const loopEl = $("#loopCount");
    if (loopEl) loopEl.textContent = "#" + lastAct.loop + "周目";
    if (lastMsgText) lastMsgText.textContent = d.last_message;
    if (lastMsgDrops) lastMsgDrops.innerHTML = (lastAct.drops || []).map(renderDropTag).join("");
  } else if (d.last_message) {
    if (noResult) noResult.style.display = "none";
    if (lastMsg) lastMsg.style.display = "flex";
    const loopEl = $("#loopCount");
    if (loopEl) loopEl.textContent = "";
    if (lastMsgText) lastMsgText.textContent = d.last_message;
    if (lastMsgDrops) lastMsgDrops.innerHTML = "";
  } else {
    if (noResult) noResult.style.display = "block";
    if (lastMsg) lastMsg.style.display = "none";
  }

  // アクティビティログ
  const log = d.activity_log || [];
  if (activityLog) {
    const html = log.slice(0, 15).map((a) =>
      '<div class="activity-item"><span class="loop">#' + escapeHtml(String(a.loop)) +
      "周目</span><span class=\"msg\">" + escapeHtml(a.msg || "") +
      '</span><div class="drops">' + (a.drops || []).map(renderDropTag).join("") + "</div></div>"
    ).join("");
    activityLog.innerHTML = html;
    activityLog.style.display = html ? "block" : "none";
    const shouldScroll = autoScrollToggle?.checked && html;
    if (activityScroll && shouldScroll) {
      requestAnimationFrame(() => {
        activityScroll.scrollTop = activityScroll.scrollHeight;
      });
    }
  }
  if (activityEmpty) {
    activityEmpty.style.display = log.length === 0 ? "block" : "none";
  }

  // 統計タブ
  if (statsLoop) statsLoop.textContent = (d.loop_count || 0).toLocaleString();
  if (statsDrops) statsDrops.textContent = (d.drops || []).length.toLocaleString();

  // 最終同期
  if (lastSyncEl) lastSyncEl.textContent = "最終更新: " + fmtLastSync(lastSyncAt);
}

async function syncState() {
  try {
    const r = await fetch("/api/state");
    if (r.ok) {
      const d = await r.json();
      setUIFromState(d);
      hideLoading();
      if (wasOffline) {
        showReconnectToast();
        wasOffline = false;
      }
      return true;
    }
    if (!navigator.onLine) return false;
    setStatusText("同期失敗 (" + r.status + ") - 再接続を試行中");
    if (st) st.setAttribute("aria-busy", "false");
  } catch (e) {
    if (navigator.onLine) {
      setStatusText("同期失敗 - 再接続を試行中");
      if (st) st.setAttribute("aria-busy", "false");
    }
  }
  return false;
}

function setupEventSource() {
  const es = new EventSource("/api/events");
  es.onopen = async () => {
    const ok = await syncState();
    if (!ok) {
      setStatusText("接続済み - 準備OK");
      st?.classList.remove("running", "lucky");
      st?.classList.add("ready");
      if (st) st.setAttribute("aria-busy", "false");
    }
    hideLoading();
  };
  es.onerror = () => {
    setStatusText("再接続中...");
    st?.classList.remove("ready", "running", "lucky");
    if (st) st.setAttribute("aria-busy", "true");
    syncState();
  };
  es.addEventListener("lucky_chance", (e) => {
    try {
      const d = JSON.parse(e.data || "{}");
      setUIFromState({ ...d, running: false, lucky: true });
      if (sb) { sb.disabled = false; sb.textContent = "▶ 再開"; }
      if (sp) sp.disabled = true;
      if (Notification.permission === "granted") {
        new Notification("あるけみすと", { body: "ラッキーチャンス！" });
      }
    } catch (err) { console.error("lucky_chance parse error:", err); }
  });
  es.addEventListener("exploration_started", (e) => {
    try {
      const d = JSON.parse(e.data || "{}");
      setUIFromState({ ...d, running: true, lucky: false });
      if (sb) sb.disabled = true;
      if (sp) sp.disabled = false;
    } catch (err) { console.error("exploration_started parse error:", err); }
  });
  es.addEventListener("exploration_stopped", (e) => {
    goPending = false;
    try {
      const d = JSON.parse(e.data || "{}");
      setUIFromState({ ...d, running: false, lucky: false });
      if (sb) sb.disabled = false;
      if (sp) sp.disabled = true;
    } catch (err) { console.error("exploration_stopped parse error:", err); }
  });
  es.addEventListener("exploration_log", (e) => {
    try { setUIFromState(JSON.parse(e.data || "{}")); } catch (err) { console.error("exploration_log parse error:", err); }
  });
}

function setupStartBtn() {
  sb?.addEventListener("click", async () => {
    if (sb.disabled) return;
    sb.disabled = true;
    goPending = true;
    clientStartMs = Date.now();
    if (sp) sp.disabled = false;
    if (timerId) clearInterval(timerId);
    timerId = setInterval(() => {
      if (statTime) statTime.textContent = fmtElapsed(Date.now() - clientStartMs);
    }, TIMER_INTERVAL_MS);
    if (statTime) statTime.textContent = fmtElapsed(0);
    try {
      const r = await fetch("/api/go", { method: "POST" });
      if (r.ok) setStatusText("送信完了 - 探索開始を待機中");
      else throw new Error("HTTP " + r.status);
    } catch (e) {
      sb.disabled = false;
      goPending = false;
      clientStartMs = null;
      if (timerId) { clearInterval(timerId); timerId = null; }
      setStatusText("接続エラー - サーバーを確認してください");
      if (st) st.setAttribute("aria-busy", "false");
    }
  });
}

function setupStopBtn() {
  sp?.addEventListener("click", async () => {
    if (sp.disabled) return;
    try {
      const r = await fetch("/api/stop-exploration", { method: "POST" });
      if (r.ok) setStatusText("停止予約 - このループ終了後に停止します");
      else throw new Error("HTTP " + r.status);
    } catch (e) {
      setStatusText("接続エラー - 停止できませんでした");
      if (st) st.setAttribute("aria-busy", "false");
    }
  });
}

function setupDropControls() {
  sortDropsBtn?.addEventListener("click", () => {
    dropsSortOrder = dropsSortOrder === "default" ? "rank-desc" : dropsSortOrder === "rank-desc" ? "rank-asc" : "default";
    setUIFromState(lastState);
  });
  dropFilter?.addEventListener("change", () => setUIFromState(lastState));
}

function setupKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.repeat) {
      if (sb && !sb.disabled) sb.click();
    }
    if (e.key === "Escape" && !e.repeat) {
      if (helpModal && !helpModal.hidden) closeHelp();
      else if (sp && !sp.disabled) sp.click();
    }
    if (e.key === "t" || e.key === "T") {
      if (e.ctrlKey || e.metaKey) return;
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") return;
      toggleTheme();
    }
    if (e.key === "?") {
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") return;
      openHelp();
    }
  });
}

// 初期化
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  tb?.addEventListener("click", toggleTheme);
  helpBtn?.addEventListener("click", openHelp);
  helpClose?.addEventListener("click", closeHelp);
  helpModal?.querySelector(".modal-backdrop")?.addEventListener("click", closeHelp);
  const luckySoundCb = $("#luckySoundToggle");
  if (luckySoundCb) {
    luckySoundCb.checked = luckySoundEnabled;
    luckySoundCb.addEventListener("change", () => {
      luckySoundEnabled = luckySoundCb.checked;
      localStorage.luckySound = luckySoundEnabled ? "1" : "0";
    });
  }
  setupTabs();
  switchTab("dashboard");
  setupDropControls();
  setupKeyboard();

  if (loadingOverlay) {
    loadingOverlay.style.display = "block";
    setTimeout(hideLoading, 5000);
  }

  window.addEventListener("online", () => {
    if (off) off.style.display = "none";
    wasOffline = true;
  });
  window.addEventListener("offline", () => {
    if (off) off.style.display = "block";
    setStatusText("オフライン");
    if (st) st.setAttribute("aria-busy", "false");
  });

  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }

  syncState();
  setInterval(syncState, SYNC_INTERVAL_MS);
  setInterval(() => {
    if (lastSyncEl && lastSyncAt) lastSyncEl.textContent = "最終更新: " + fmtLastSync(lastSyncAt);
  }, 10000);
  setupEventSource();
  setupStartBtn();
  setupStopBtn();
});
