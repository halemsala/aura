// hud-overlay.js — HUD unificado: estado da extensão + Local AI :8765
(function () {
  if (window.__auraHudLoaded) return;
  window.__auraHudLoaded = true;

  function el(id) { return document.getElementById(id); }

  function criarHUD() {
    if (el("aura-hud-container")) return;
    const box = document.createElement("div");
    box.id = "aura-hud-container";
    box.style.cssText = "position:fixed;top:15px;right:15px;z-index:999999;background:rgba(10,15,26,0.92);backdrop-filter:blur(8px);border:1px solid #00f0ff;border-radius:10px;padding:14px 18px;color:#fff;font-family:Segoe UI,monospace;width:290px;box-shadow:0 8px 32px rgba(0,240,255,0.2);font-size:12px;";
    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1f293d;padding-bottom:6px;margin-bottom:8px;">
        <b style="color:#00f0ff;font-size:13px;">AURA QUANT-X</b>
        <span id="aura-status" style="color:#ffbb00;font-size:10px;">● INICIANDO</span>
      </div>
      <div><b>Sinal:</b> <span id="aura-signal" style="color:#888;">—</span></div>
      <div><b>Prob. Canto:</b> <span id="aura-corner-prob">0.0%</span></div>
      <div><b>Prob. Gol:</b> <span id="aura-goal-prob">0.0%</span></div>
      <div><b>Stake Kelly:</b> <span id="aura-kelly">0.0%</span></div>
      <div><b>Partida:</b> <span id="aura-match" style="color:#9ca3af;">—</span></div>
      <div style="margin-top:6px;font-size:10px;color:#6b7280;"><span id="aura-meta">aguardando</span></div>
    `;
    const root = document.body || document.documentElement;
    if (!root) {
      document.addEventListener("DOMContentLoaded", () => {
        const r2 = document.body || document.documentElement;
        if (r2 && !document.getElementById("aura-hud-container")) r2.appendChild(box);
      }, { once: true });
      return;
    }
    root.appendChild(box);
  }

  function setStatus(text, color) {
    const s = el("aura-status");
    if (s) { s.textContent = text; s.style.color = color || "#ffbb00"; }
  }

  function setText(id, text, color) {
    const n = el(id);
    if (!n) return;
    n.textContent = text;
    if (color) n.style.color = color;
  }

  function heuristicFromState(st) {
    const stats = st.stats || {};
    const corners = stats.corners || {};
    const dangerous = stats.dangerous || {};
    const xg = stats.xg || {};
    const minute = Number(st.minute) || 1;
    const cH = Number(corners.home) || 0, cA = Number(corners.away) || 0;
    const dH = Number(dangerous.home) || 0, dA = Number(dangerous.away) || 0;
    const xH = Number(xg.home) || 0, xA = Number(xg.away) || 0;
    const rate = (cH + cA) / Math.max(minute, 1);
    const pressure = (dH + dA) / Math.max(minute, 1);
    let cornerP = Math.min(0.92, 0.12 + rate * 0.35 + pressure * 0.02 + (xH + xA) * 0.08);
    let goalP = Math.min(0.85, 0.08 + (xH + xA) * 0.25 + pressure * 0.01);
    const signal = cornerP >= 0.55 ? "WATCH_CORNER" : goalP >= 0.45 ? "WATCH_GOAL" : "HOLD";
    const kelly = Math.max(0, Math.min(0.08, (cornerP - 0.45) * 0.25));
    return { signal, corner_prob: cornerP, goal_prob: goalP, kelly };
  }

  async function pullExtensionState() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "REQUEST_STATE" }, (res) => {
          if (chrome.runtime.lastError) return resolve(null);
          resolve(res || null);
        });
      } catch (e) { resolve(null); }
    });
  }

  async function pullLocalAI(fixtureId) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "LOCAL_AI_ANALYSIS", fixtureId: fixtureId || null }, (res) => {
          if (chrome.runtime.lastError) return resolve(null);
          resolve(res?.ok ? (res.analysis || res.data || null) : null);
        });
      } catch (_) { resolve(null); }
    });
  }

  async function tick() {
    criarHUD();
    const st = await pullExtensionState();
    const live = st && st.fixtureId && (st.liveStatus === "live" || st.capture?.armed);
    if (!live) {
      setStatus("● SEM PARTIDA", "#ff4444");
      setText("aura-signal", "AGUARDANDO CAPTURA", "#888");
      setText("aura-match", "abra SokkerPRO + Capturar");
      setText("aura-meta", "extensão sem fixture ativo");
      return;
    }

    const ai = await pullLocalAI(st.fixtureId);
    let signal = "HOLD", cornerP = 0, goalP = 0, kelly = 0, src = "heuristica";

    if (ai && (ai.signal || ai.corner_prob != null || ai.analytics || (ai.ok && ai.fixtureId))) {
      const a = ai.analysis || ai;
      const an = a.analytics || ai.analytics || {};
      signal = a.signal || ai.signal || "HOLD";
      cornerP = Number(a.corner_prob != null ? a.corner_prob : (an.probabilidadeEscanteio5Min != null ? an.probabilidadeEscanteio5Min : ai.corner_prob)) || 0;
      goalP = Number(a.goal_prob != null ? a.goal_prob : (an.probabilidadeGol != null ? an.probabilidadeGol : ai.goal_prob)) || 0;
      kelly = Number(a.kelly != null ? a.kelly : (an.gestaoKellyRecomendada != null ? an.gestaoKellyRecomendada : ai.kelly)) || 0;
      src = "local-ai:8765";
      setStatus("● IA LOCAL", "#00ff88");
    } else {
      const h = heuristicFromState(st);
      signal = h.signal; cornerP = h.corner_prob; goalP = h.goal_prob; kelly = h.kelly;
      src = "heuristica+captura";
      setStatus("● CAPTURA OK", "#00ff88");
    }

    const sigColor = signal.includes("BUY") || signal.includes("WATCH") ? "#00ff88" : "#ffbb00";
    setText("aura-signal", signal, sigColor);
    setText("aura-corner-prob", (cornerP * 100).toFixed(1) + "%");
    setText("aura-goal-prob", (goalP * 100).toFixed(1) + "%");
    setText("aura-kelly", (kelly * 100).toFixed(1) + "%");
    setText("aura-match", (st.home || "?") + " " + (st.score?.home ?? 0) + "×" + (st.score?.away ?? 0) + " " + (st.away || "?") + " · " + (st.minute != null ? st.minute + "'" : "—"));
    setText("aura-meta", src + " · snaps " + (st.capture?.acceptedSnapshots || st.snapshotCount || 0) + " · " + (st.fixtureId || ""));
  }

  criarHUD();
  tick();
  setInterval(tick, 2000);
})();
