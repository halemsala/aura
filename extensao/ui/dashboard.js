function safeBody(){return document.body||document.documentElement;}
/**
 * CornerAI Dashboard — Refactored Architecture (v12.6.17)
 * Front-end Architecture Expert: batched RAF single-flight updates,
 * differential text patches, stable element cache, strict validation gate
 * before AI hand-off. Eliminates layout thrashing, infinite re-render cascades
 * and DOM reference collapse.
 */
(() => {
  "use strict";

  /* ───────────────────────── Constants & Labels ───────────────────────── */
  const KEYS = ["attacks","dangerous","shots","shotsOn","shotsOff","corners","xg","fouls","offsides","yellow","red","subs","crosses","saves","passes","passesFailed","possession"];
  const LABELS = {
    attacks:"Ataques", dangerous:"Ataques perigosos", shots:"Finalizações", shotsOn:"No alvo",
    shotsOff:"Fora", corners:"Escanteios", xg:"xG", fouls:"Faltas", offsides:"Impedimentos",
    yellow:"Amarelos", red:"Vermelhos", subs:"Substituições", crosses:"Cruzamentos",
    saves:"Defesas", passes:"Passes certos", passesFailed:"Passes errados", possession:"Posse (%)"
  };
  const METRIC_LABELS = { ...LABELS };

  const INTEGRITY_CHECK_DETAILS = {
    "clock":{title:"Relógio da partida",pass:"Minuto de jogo capturado e finito.",fail:"Minuto ausente ou inválido. Sem relógio a IA não ancora pressão nem cantos no tempo.",fix:"Confirme que a página da partida está aberta e o placar/relógio visíveis no SokkerPRO."},
    "fixture":{title:"Fixture e times",pass:"ID da partida + mandante + visitante identificados.",fail:"Falta fixtureId ou nome de um dos times. Isolamento e H2H ficam comprometidos.",fix:"Abra a URL da partida (não só livescores) e arme a captura pelo popup."},
    "corners-stats-events":{title:"Cantos · stats vs eventos",pass:"Contagem do painel alinhada à cronologia (lag ≤ 2).",fail:"Eventos > stats (inflado) ou stats − eventos > 2 (cronologia atrasada/perdida).",fix:"Force captura ou recarregue a extensão; a re-hidratação deve recuperar minutos faltantes."},
    "no-future-events":{title:"Sem eventos futuros",pass:"Nenhum evento com minuto > relógio+2.",fail:"Há eventos à frente do relógio (ex.: canto 37' com jogo em 21'). Contamina a IA.",fix:"Filtro 4.88.42+. Se persistir, o DOM ainda expõe texto futuro."},
    "corners-ordered":{title:"Ordem cronológica dos cantos",pass:"Cantos em ordem crescente de minuto.",fail:"Lista fora de ordem temporal.",fix:"Force captura; se repetir, há assinaturas duplicadas conflitantes."},
    "pressure-dual":{title:"Pressão dual válida",pass:"Barras com home e away > 0 (sem 72%×0%).",fail:"Intervalo com um lado zerado ou vazio residual.",fix:"Filtros de vela 4.88.37+. Verifique menu GRÁFICOS / pressure_bar."},
    "score":{title:"Placar",pass:"Placar home/away numérico.",fail:"Placar ausente ou não numérico.",fix:"O título da página costuma ser a fonte mais estável; recarregue a partida."},
    "freshness":{title:"Atualização recente",pass:"Último snapshot dentro do limite (15s normal / 5s crítico).",fail:"Dados stale — captura parada ou aba em background.",fix:"Mantenha a aba SokkerPRO ativa; modo crítico acelera em 30'–45' e 80'–90'."},
    "minute-coverage":{title:"Cobertura de minutos",pass:"Sem furos na sequência de minutos observados.",fail:"Há minutos sem snapshot (gap).",fix:"Modo crítico e heartbeat reduzem gaps. Gaps curtos em intervalo normal podem ser aceitáveis."}
  };

  /* ───────────────────────── Stable Element Cache ───────────────────────── */
  const els = Object.create(null);
  function $(id) {
    if (!els[id] || !document.contains(els[id])) {
      els[id] = document.getElementById(id);
    }
    return els[id];
  }

  /* ───────────────────────── RAF Single-Flight Scheduler ───────────────────────── */
  let pendingState = null;
  let rafId = 0;
  let lastRenderedVersion = -1;

  function scheduleUpdate(state) {
    if (!state) return;
    pendingState = state;
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      const s = pendingState;
      pendingState = null;
      if (!s) return;
      const ver = Number(s.stateVersion || s.lastUpdate || 0);
      if (ver === lastRenderedVersion && s === window.__corneraiState) return;
      lastRenderedVersion = ver;
      window.__corneraiState = s;
      performBatchedRender(s);
      if (typeof window.__corneraiVisualUpdate === "function") {
        window.__corneraiVisualUpdate(s);
      }
    });
  }

  /* ───────────────────────── Strict Validation Gate (pre-export) ───────────────────────── */
  function isFiniteNumber(v) {
    return typeof v === "number" && Number.isFinite(v);
  }
  function isNonEmptyString(v) {
    return typeof v === "string" && v.trim().length > 0;
  }
  function validatePayloadForExport(state) {
    const errors = [];
    if (!state || typeof state !== "object") {
      errors.push({ field: "root", rule: "object", detail: "Estado nulo ou inválido" });
      return { ok: false, errors };
    }
    if (!isNonEmptyString(state.fixtureId) && !isNonEmptyString(state.home)) {
      errors.push({ field: "fixtureId|home", rule: "required", detail: "Identificação de partida ausente" });
    }
    if (state.minute != null && !isFiniteNumber(Number(state.minute))) {
      errors.push({ field: "minute", rule: "finite", detail: "Relógio inválido" });
    }
    if (state.score) {
      if (!isFiniteNumber(Number(state.score.home)) || !isFiniteNumber(Number(state.score.away))) {
        errors.push({ field: "score", rule: "numeric-pair", detail: "Placar não numérico" });
      }
    }
    const events = Array.isArray(state.cornerEvents) ? state.cornerEvents : [];
    const clock = Number(state.minute);
    if (Number.isFinite(clock)) {
      for (const e of events) {
        const m = Number(e.minute);
        if (Number.isFinite(m) && m > clock + 2) {
          errors.push({ field: "cornerEvents", rule: "no-future", detail: `Evento futuro ${m}' com relógio ${clock}'` });
          break;
        }
      }
    }
    let prev = -1;
    for (const e of events.slice().sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)))) {
      const key = (e.period || 0) * 200 + (e.minute || 0) + ((e.extraMinute || 0) / 100);
      if (key < prev - 0.01) {
        errors.push({ field: "cornerEvents", rule: "ordered", detail: "Ordem cronológica quebrada" });
        break;
      }
      prev = key;
    }
    if (errors.length) return { ok: false, errors };
    return { ok: true, errors: [] };
  }

  /* ───────────────────────── AI Hand-off with Validation Gate ───────────────────────── */
  const aiSendButton = $("sendAI");
  if (aiSendButton) {
    aiSendButton.addEventListener("click", async () => {
      aiSendButton.disabled = true;
      const old = aiSendButton.textContent;
      aiSendButton.textContent = "VALIDANDO…";
      try {
        const r = await chrome.runtime.sendMessage({ type: "AI_HANDOFF_REQUEST" });
        if (!r?.ok) throw new Error(r?.error || "Falha ao preparar feed");

        const gate = validatePayloadForExport(r.feed || r.state || window.__corneraiState);
        if (!gate.ok) {
          console.error("[CornerAI][ValidationGate]", gate.errors);
          aiSendButton.textContent = "DADOS INVÁLIDOS";
          aiSendButton.title = gate.errors.map(e => `${e.field}: ${e.detail}`).join(" | ");
          setTimeout(() => { aiSendButton.textContent = old; aiSendButton.disabled = false; }, 2200);
          return;
        }

        const payload = JSON.stringify(r.feed, null, 2);
        try {
          await navigator.clipboard.writeText(payload);
          aiSendButton.textContent = "ENVIADO · COPIADO";
        } catch (_) {
          aiSendButton.textContent = "FEED PRONTO";
        }
        aiSendButton.title = "Feed AI validado e armazenado. Pronto para consumo.";
        setTimeout(() => { aiSendButton.textContent = old; aiSendButton.disabled = false; }, 1800);
      } catch (e) {
        aiSendButton.textContent = "ERRO AO ENVIAR";
        setTimeout(() => { aiSendButton.textContent = old; aiSendButton.disabled = false; }, 1800);
      }
    });
  }

  /* ───────────────────────── Panel Construction (once only) ───────────────────────── */
  const health = document.createElement("section");
  health.id = "healthPanel";
  health.className = "panel";
  health.innerHTML = "<h2>Saúde da captura · diagnóstico em tempo real</h2><div id='healthGrid'></div>";
  safeBody()&&safeBody().appendChild(health);

  const stats = $("stats");
  if (stats) {
    stats.innerHTML = "";
    const statsTitle = document.createElement("h2");
    statsTitle.textContent = "Dados separados por equipe";
    stats.appendChild(statsTitle);
    const grid = document.createElement("div");
    grid.className = "team-stats-grid";
    for (const side of ["home", "away"]) {
      const card = document.createElement("section");
      card.className = "team-card";
      card.id = `team-${side}`;
      const h = document.createElement("h3");
      h.id = `teamName-${side}`;
      h.textContent = side === "home" ? "CASA" : "VISITANTE";
      card.appendChild(h);
      const table = document.createElement("div");
      table.className = "team-stat-table";
      for (const k of KEYS) {
        const r = document.createElement("div");
        r.className = "team-stat-row";
        const label = document.createElement("span");
        label.textContent = LABELS[k];
        const val = document.createElement("b");
        val.id = `${k}-${side}`;
        val.textContent = "—";
        r.append(label, val);
        table.appendChild(r);
      }
      card.appendChild(table);
      grid.appendChild(card);
    }
    stats.appendChild(grid);
  }

  const timeline = document.createElement("section");
  timeline.id = "cornerTimeline";
  timeline.className = "panel";
  timeline.innerHTML = '<h2 title="🚩 Mostra quando cada equipe ganhou escanteios">🚩 Escanteios por equipe · ordem cronológica <span class="help-icon" title="🚩 Exibe os escanteios por equipe e em ordem de ocorrência.">ⓘ</span></h2><div class="corner-columns"><div><h3 id="cornerHomeTitle">Casa</h3><ol id="cornerHome"></ol></div><div><h3 id="cornerAwayTitle">Visitante</h3><ol id="cornerAway"></ol></div></div>';
  safeBody()&&safeBody().appendChild(timeline);

  const graph = document.createElement("section");
  graph.id = "cornerGraph";
  graph.className = "panel";
  graph.innerHTML = "<div class='chart-head'><div><span class='chart-kicker'>EVENTOS CRONOLÓGICOS</span><h2>Escanteios · acumulado por minuto</h2><p>Curva construída exclusivamente a partir dos eventos de canto aceitos.</p></div><div class='chart-live'><i></i> DADOS OBSERVADOS</div></div><div id='graphLegend'><span class='legend-home'>● Mandante</span><span class='legend-away'>● Visitante</span></div><svg id='cornerSvg' viewBox='0 0 900 280' preserveAspectRatio='none' role='img' aria-label='Escanteios acumulados por minuto'></svg><div id='graphData'></div>";
  safeBody()&&safeBody().appendChild(graph);

  const livePanel = document.createElement("section");
  livePanel.id = "liveCapturePanel";
  livePanel.className = "panel";
  livePanel.innerHTML = `<div class="live-capture-head"><div><span class="chart-kicker">CAPTURA AUTOMÁTICA</span><h2 id="liveCaptureTitle">Aguardando partida</h2><p id="liveCaptureSub">O motor inicia sozinho quando uma partida SokkerPRO é detectada.</p></div><div class="live-capture-actions"><button id="liveCaptureNow" type="button">↻ Atualizar captura</button><button id="liveCaptureDiagnose" type="button">Diagnóstico</button></div></div><div class="live-capture-grid"><div><span>Fixture</span><b id="liveFixture">—</b></div><div><span>Status</span><b id="liveStatus">—</b></div><div><span>Minuto</span><b id="liveMinuteDash">—</b></div><div><span>Snapshots</span><b id="liveSnapshotsDash">0</b></div><div><span>Eventos</span><b id="liveEventsDash">0</b></div><div><span>Fonte</span><b id="liveSourceDash">—</b></div></div>`;
  document.body.prepend(livePanel);

  const historyPanel = document.createElement("section");
  historyPanel.className = "panel";
  historyPanel.id = "teamHistoryPanel";
  historyPanel.innerHTML = '<h2>Gráficos históricos separados por equipe</h2><div class="history-controls"><label>Indicador <select id="historyMetric"></select></label></div><svg id="historySvg" viewBox="0 0 900 300" role="img" aria-label="Histórico do indicador por equipe"></svg><div id="historyData"></div>';
  safeBody()&&safeBody().appendChild(historyPanel);

  const ledgerPanel = document.createElement("section");
  ledgerPanel.className = "panel";
  ledgerPanel.id = "statLedgerPanel";
  ledgerPanel.innerHTML = '<h2>Alterações históricas por equipe</h2><div id="statLedger"></div>';
  safeBody()&&safeBody().appendChild(ledgerPanel);

  const eventPanel = document.createElement("section");
  eventPanel.className = "panel";
  eventPanel.id = "unifiedEventPanel";
  eventPanel.innerHTML = '<h2 title="🧾 Reúne eventos e mudanças estatísticas">🧾 Timeline unificada · eventos da partida <span class="help-icon" title="🧾 Junta eventos da partida e alterações de métricas em uma única linha do tempo.">ⓘ</span></h2><div id="unifiedEventList"></div>';
  safeBody()&&safeBody().appendChild(eventPanel);

  const contextPanel = document.createElement("section");
  contextPanel.className = "panel";
  contextPanel.id = "cornerContextPanel";
  contextPanel.innerHTML = '<h2>Contexto dos escanteios · 10 minutos anteriores</h2><div id="cornerContextList"></div>';
  safeBody()&&safeBody().appendChild(contextPanel);

  const oddsPanel = document.createElement("section");
  oddsPanel.className = "panel";
  oddsPanel.id = "oddsHistoryPanel";
  oddsPanel.innerHTML = '<h2>Precificação do mercado · histórico por minuto</h2><div id="oddsSummary"></div><div id="oddsList"></div>';
  safeBody()&&safeBody().appendChild(oddsPanel);

  const cornerIndicatorPanel = document.createElement("section");
  cornerIndicatorPanel.className = "panel";
  cornerIndicatorPanel.id = "cornerIndicatorPanel";
  cornerIndicatorPanel.innerHTML = '<h2>Indicadores de pressão para escanteios · captura por minuto</h2><div id="cornerIndicatorSummary"></div><div id="cornerIndicatorHistory"></div>';
  safeBody()&&safeBody().appendChild(cornerIndicatorPanel);

  const metricSelect = $("historyMetric");
  if (metricSelect) {
    Object.entries(METRIC_LABELS).forEach(([k, v]) => {
      const o = document.createElement("option");
      o.value = k;
      o.textContent = v;
      metricSelect.appendChild(o);
    });
    metricSelect.value = "corners";
    metricSelect.addEventListener("change", () => {
      if (window.__corneraiState) renderHistory(window.__corneraiState);
    });
  }

  /* ───────────────────────── Pure Helpers ───────────────────────── */
  function led(id, on) {
    const e = $(id);
    if (e) e.className = on ? "on" : "off";
  }
  function fmtMinute(e) {
    return `${e.minute}${e.extraMinute ? `+${e.extraMinute}` : ""}'`;
  }
  function escEvents(events, side) {
    return (Array.isArray(events) ? events : [])
      .filter(e => e.side === side)
      .sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)));
  }
  function setText(id, text) {
    const e = $(id);
    if (e && e.textContent !== String(text)) e.textContent = String(text);
  }

  function eventStableKey(e, i) {
    // Chave estável para reconciliação: id nativo > fingerprint de minuto/periodo/lado/fonte
    if (e && (e.id != null || e.eventId != null)) return String(e.id ?? e.eventId);
    return `m${e?.minute ?? "?"}_x${e?.extraMinute ?? 0}_p${e?.period ?? 0}_s${e?.side || ""}_src${e?.source || ""}_i${i}`;
  }

  function renderList(id, titleId, events) {
    const box = $(id);
    if (!box) return;
    const h = $(titleId);
    if (h) h.textContent = `${events.length} escanteios`;
    if (!events.length) {
      if (box.childElementCount !== 1 || box.firstChild?.textContent !== "Nenhum evento capturado.") {
        box.innerHTML = "";
        const li = document.createElement("li");
        li.textContent = "Nenhum evento capturado.";
        box.appendChild(li);
      }
      return;
    }
    // [FIX v12.6.17] reconciliação chaveada:
    // cria só nós novos, remove só obsoletos, atualiza texto in-place nos que permanecem.
    const wanted = new Map();
    events.forEach((e, i) => {
      const key = eventStableKey(e, i);
      const text = `${i + 1}. ${fmtMinute(e)} · ${e.period === 1 ? "1º tempo" : "2º tempo"} · ${e.source || "fonte"}`;
      wanted.set(key, text);
    });
    const existing = new Map();
    Array.from(box.children).forEach(node => {
      const k = node.dataset?.key;
      if (k) existing.set(k, node);
    });
    // Remove obsoletos
    for (const [k, node] of existing) {
      if (!wanted.has(k)) node.remove();
    }
    // Cria / atualiza na ordem
    let cursor = box.firstChild;
    for (const [key, text] of wanted) {
      let node = existing.get(key);
      if (!node) {
        node = document.createElement("li");
        node.dataset.key = key;
        node.textContent = text;
        box.insertBefore(node, cursor);
      } else {
        if (node.textContent !== text) node.textContent = text;
        // Garante ordem: se não estiver na posição certa, move
        if (node !== cursor) {
          box.insertBefore(node, cursor);
        } else {
          cursor = node.nextSibling;
        }
        continue;
      }
      cursor = node.nextSibling;
    }
  }

  function renderGraph(s) {
    const svg = $("cornerSvg");
    if (!svg) return;
    svg.innerHTML = "";
    const all = Array.isArray(s.cornerEvents)
      ? s.cornerEvents.slice().sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)))
      : [];
    const maxMinute = Math.max(90, ...all.map(e => Number(e.minute) || 0), Number(s.minute) || 0);
    const W = 900, H = 280, L = 55, R = 20, T = 20, B = 45, gw = W - L - R, gh = H - T - B;
    const maxCount = Math.max(1, all.length, Number(s.stats?.corners?.home || 0), Number(s.stats?.corners?.away || 0));
    const ns = "http://www.w3.org/2000/svg";
    const line = (x1, y1, x2, y2) => {
      const el = document.createElementNS(ns, "line");
      el.setAttribute("x1", x1); el.setAttribute("y1", y1); el.setAttribute("x2", x2); el.setAttribute("y2", y2);
      el.setAttribute("stroke", "currentColor"); el.setAttribute("stroke-opacity", ".25");
      return el;
    };
    svg.appendChild(line(L, T, L, T + gh));
    svg.appendChild(line(L, T + gh, W - R, T + gh));
    for (let i = 0; i <= 6; i++) {
      const x = L + gw * i / 6;
      const lab = document.createElementNS(ns, "text");
      lab.setAttribute("x", x); lab.setAttribute("y", H - 12); lab.setAttribute("text-anchor", "middle");
      lab.textContent = Math.round(maxMinute * i / 6) + "'";
      svg.appendChild(lab);
    }
    for (let i = 0; i <= maxCount; i++) {
      const y = T + gh - (gh * i / maxCount);
      const lab = document.createElementNS(ns, "text");
      lab.setAttribute("x", L - 8); lab.setAttribute("y", y + 4); lab.setAttribute("text-anchor", "end");
      lab.textContent = i;
      svg.appendChild(lab);
    }
    for (const side of ["home", "away"]) {
      let count = 0;
      const pts = [];
      for (const e of all.filter(e => e.side === side)) {
        count++;
        const x = L + gw * ((e.minute + (e.extraMinute || 0) / 10) / maxMinute);
        const y = T + gh - gh * (count / maxCount);
        pts.push([x, y]);
      }
      const poly = document.createElementNS(ns, "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", "currentColor");
      poly.setAttribute("stroke-width", "3");
      poly.setAttribute("class", side === "home" ? "home-line" : "away-line");
      poly.setAttribute("stroke-dasharray", side === "away" ? "7 5" : "none");
      poly.setAttribute("points", pts.map(p => p.join(",")).join(" "));
      svg.appendChild(poly);
      pts.forEach(p => {
        const c = document.createElementNS(ns, "circle");
        c.setAttribute("cx", p[0]); c.setAttribute("cy", p[1]); c.setAttribute("r", "4");
        c.setAttribute("fill", "currentColor");
        c.setAttribute("class", side === "home" ? "home-line" : "away-line");
        svg.appendChild(c);
      });
    }
    const data = $("graphData");
    if (data) {
      data.textContent = `Dados do gráfico: ${s.home || "Casa"} = ${(s.teamData?.home?.cornerMinutes || []).map(e => fmtMinute(e)).join(", ") || "—"} · ${s.away || "Visitante"} = ${(s.teamData?.away?.cornerMinutes || []).map(e => fmtMinute(e)).join(", ") || "—"}`;
    }
  }

  function renderHealth(s) {
    const box = $("healthGrid");
    if (!box) return;
    const q = s.quality || {}, cap = s.capture || {}, ch = s.captureHealth || {}, m = ch.metrics || {}, sig = ch.signals || {}, reject = Number(m.rejected || 0);
    const integ = s.integrity || s.analyst?.quality || {};
    const rows = [
      ["Saúde da captura", `${ch.score ?? q.score ?? 0}/100 · ${ch.status || q.grade || "—"}`],
      ["Integridade", `${integ.integrityScore ?? "—"} /100 · ${integ.pass === true ? "PASS" : (integ.pass === false ? "FAIL" : "—")}`],
      ["Estado", String(s.liveStatus || "—")],
      ["Fonte", String(s.lastSnapshotSource || "—")],
      ["Último dado", ch.ageMs == null ? "—" : `${(Number(ch.ageMs) / 1000).toFixed(1)}s`],
      ["Snapshots", String(m.snapshots ?? s.statTimeline?.length ?? 0)],
      ["Aceitos", String(m.accepted ?? cap.acceptedSnapshots ?? 0)],
      ["Rejeições", String(reject)],
      ["Conflitos", String(m.conflicts ?? 0)],
      ["Sessão", sig.session?.label || "—"],
      ["Content Script", sig.contentScript?.label || "—"],
      ["Fixture", sig.fixture?.label || "—"],
      ["Hook", sig.hook?.label || "—"],
      ["Rede", sig.network?.label || "—"],
      ["Persistência", sig.persistence?.label || "—"],
      ["Menus", sig.menus?.label || "—"],
      ["Parâmetros extras", String(Object.keys(s.extendedStats || {}).length)],
      ["Erros", String(s.errors?.length || 0)],
      ["AI Feed", s.aiFeed?.schema || "cornerai-ai-feed-11"],
      ["Analyst", s.analyst?.schema || "cornerai-analyst-1"]
    ];
    let html = rows.map(([a, b]) => `<div class='health-item'><span>${a}</span><b>${b}</b></div>`).join("");
    const checks = Array.isArray(integ.checks) ? integ.checks : [];
    if (checks.length) {
      html += `<div class="integrity-table-wrap"><div class="integrity-title">Checks automáticos de integridade</div>`;
      html += `<table class="integrity-table"><thead><tr><th>Check</th><th>Status</th><th>Detalhe · significado · correção</th></tr></thead><tbody>`;
      for (const ck of checks) {
        const ok = !!ck.ok;
        const meta = INTEGRITY_CHECK_DETAILS[ck.id] || { title: ck.id || "—", pass: "", fail: "", fix: "" };
        const explain = ok ? meta.pass : meta.fail;
        html += `<tr class="${ok ? "ok" : "fail"}">`;
        html += `<td><div class="ck-id">${meta.title}</div><div class="ck-key">${ck.id || ""}</div></td>`;
        html += `<td>${ok ? "PASS" : "FAIL"}</td>`;
        html += `<td><div class="ck-detail">${String(ck.detail || "").slice(0, 120)}</div><div class="ck-explain">${explain || ""}</div>`;
        if (!ok && meta.fix) html += `<div class="ck-fix">→ ${meta.fix}</div>`;
        html += `</td></tr>`;
      }
      html += `</tbody></table>`;
      if (integ.corners) {
        const cn = integ.corners;
        html += `<div class="integrity-meta">Cantos · stats ${cn.stats?.[0] ?? "—"}×${cn.stats?.[1] ?? "—"} · eventos ${cn.events?.[0] ?? "—"}×${cn.events?.[1] ?? "—"} · lag ${cn.lag?.[0] ?? "—"}/${cn.lag?.[1] ?? "—"}</div>`;
      }
      if (Array.isArray(integ.failed) && integ.failed.length) {
        html += `<div class="integrity-failed">Falhas: ${integ.failed.join(", ")}</div>`;
      }
      html += `</div>`;
    }
    const hist = Array.isArray(s.integrityHistory) ? s.integrityHistory : [];
    if (hist.length) {
      const scores = hist.map(h => Number(h.integrityScore) || 0);
      const minS = Math.min(...scores), maxS = Math.max(...scores);
      const latest = hist[hist.length - 1];
      const fails = hist.filter(h => !h.pass).slice(-8);
      const w = 320, h = 48, pad = 2;
      const pts = scores.map((v, i) => {
        const x = pad + (i / (Math.max(1, scores.length - 1))) * (w - 2 * pad);
        const y = h - pad - ((v - 0) / 100) * (h - 2 * pad);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      html += `<div class="integrity-monitor">`;
      html += `<div class="integrity-title">Monitoramento de integridade · tempo real</div>`;
      html += `<div class="integrity-kpis">`;
      html += `<span>Atual <b>${latest.integrityScore ?? "—"}</b></span>`;
      html += `<span>Mín <b>${minS}</b></span>`;
      html += `<span>Máx <b>${maxS}</b></span>`;
      html += `<span>Pontos <b>${hist.length}</b></span>`;
      html += `<span>Janela <b>${latest.window || "—"}</b></span>`;
      html += `</div>`;
      html += `<svg class="integrity-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline fill="none" stroke="#3ecf8e" stroke-width="2" points="${pts}"/></svg>`;
      if (fails.length) {
        html += `<div class="integrity-title" style="margin-top:8px">Falhas recentes</div>`;
        html += `<table class="integrity-table"><thead><tr><th>Min</th><th>Score</th><th>Falhas</th></tr></thead><tbody>`;
        for (const f of fails.slice().reverse()) {
          html += `<tr class="fail"><td>${f.minute ?? "—"}${f.extra ? `+${f.extra}` : ""}'</td><td>${f.integrityScore}</td><td>${(f.failed || []).join(", ") || "—"}</td></tr>`;
        }
        html += `</tbody></table>`;
      } else {
        html += `<div class="integrity-meta">Nenhuma falha na janela monitorada.</div>`;
      }
      html += `</div>`;
    }
    box.innerHTML = html;
  }

  function renderLiveCapture(s) {
    if (!s) return;
    const active = !!s.fixtureId;
    const q = Number(s.quality?.score || 0);
    setText("liveCaptureTitle", active ? `${s.home || "Casa"} × ${s.away || "Visitante"}` : "Aguardando partida");
    setText("liveCaptureSub", active
      ? `Captura ${s.liveStatus === "live" ? "ao vivo" : s.liveStatus === "finished" ? "finalizada" : "ativa"} · qualidade ${Math.round(q)}/100`
      : "Abra uma partida SokkerPRO; a captura será iniciada automaticamente.");
    setText("liveFixture", s.fixtureId || "—");
    setText("liveStatus", s.liveStatus === "live" ? "AO VIVO" : s.liveStatus === "finished" ? "FINALIZADA" : active ? "ATIVA" : "AGUARDANDO");
    setText("liveMinuteDash", s.minute == null ? "—" : `${s.minute}${s.extraMinute ? `+${s.extraMinute}` : ""}'`);
    setText("liveSnapshotsDash", String(s.snapshotCount || 0));
    setText("liveEventsDash", String(s.eventCount || s.cornerEventCount || 0));
    setText("liveSourceDash", s.lastSnapshotSource || "—");
  }

  function renderMenuCapture(s) {
    const box = $("menuCapturePanel");
    if (!box) return;
    const m = s.menuCapture || {};
    const discovered = Array.isArray(m.discovered) ? m.discovered : [];
    const recent = Array.isArray(m.history) ? m.history.slice(-10).reverse() : [];
    const labels = { pre_jogo: "PRÉ-JOGO", pre_odds: "PRÉ-ODDS", ao_vivo: "AO VIVO", graficos: "GRÁFICOS", odds: "ODDS", dicas: "DICAS", h2h: "H2H", estatisticas: "ESTATÍSTICAS", escalacoes: "ESCALAÇÕES", rank: "RANK", unknown: "OUTROS" };
    const known = ["pre_jogo", "pre_odds", "ao_vivo", "graficos", "odds", "dicas", "h2h", "estatisticas", "escalacoes", "rank"];
    const captured = new Set(Object.values(m.menus || {}).map(x => x.menuId));
    box.innerHTML = `<h2>Central de captura dos menus</h2><div class="menu-summary"><div><span>Menus descobertos</span><b>${discovered.length}</b></div><div><span>Menus capturados</span><b>${captured.size}/10</b></div><div><span>Dados coletados</span><b>${Number(m.dataPoints || 0).toLocaleString("pt-BR")}</b></div><div><span>Última captura</span><b>${m.lastCaptureAt ? new Date(m.lastCaptureAt).toLocaleTimeString("pt-BR") : "—"}</b></div></div><div class="menu-grid">${known.map(id => `<div class="menu-chip ${captured.has(id) ? "captured" : "pending"}"><i>${captured.has(id) ? "✓" : "○"}</i><span>${labels[id]}</span></div>`).join("")}</div><div class="menu-current"><b>Atual:</b> ${m.current?.menuLabel || labels[m.current?.menuId] || "Não identificado"} · <span>${m.current?.title || m.current?.url || "—"}</span></div><div class="menu-recent">${recent.length ? recent.map(r => `<div class="ledger-row"><b>${labels[r.menuId] || r.menuId}</b> · ${r.label || "—"} · ${r.textLength || 0} chars · ${r.tables || 0} tabelas · ${r.odds || 0} odds</div>`).join("") : "Nenhum menu capturado ainda."}</div>`;
  }

  function renderH2H(s) {
    const h = s?.h2h;
    if (!h?.captured) return;
    let b = $("h2hPanel");
    if (!b) {
      b = document.createElement("section");
      b.className = "panel";
      b.id = "h2hPanel";
      safeBody()&&safeBody().appendChild(b);
      els["h2hPanel"] = b;
    }
    b.innerHTML = `<h2>H2H · Escanteios</h2><div>${(h.tables || []).map(t => `<div class="ledger-row">${String(t.text || "").slice(0, 5000)}</div>`).join("") || "Sem dados"}</div>`;
  }

  function reconcileKeyedRows(box, rows, keyFn, textFn, className) {
    // Helper genérico de reconciliação chaveada para listas de divs
    if (!box) return;
    if (!rows.length) {
      if (box.childElementCount !== 1 || !box.firstChild?.classList?.contains("empty-row")) {
        box.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "empty-row";
        empty.textContent = "Nenhum item ainda.";
        box.appendChild(empty);
      }
      return;
    }
    const wanted = new Map();
    rows.forEach((r, i) => {
      const key = keyFn(r, i);
      wanted.set(key, textFn(r, i));
    });
    const existing = new Map();
    Array.from(box.children).forEach(node => {
      const k = node.dataset?.key;
      if (k) existing.set(k, node);
    });
    for (const [k, node] of existing) {
      if (!wanted.has(k)) node.remove();
    }
    let cursor = box.firstChild;
    for (const [key, text] of wanted) {
      let node = existing.get(key);
      if (!node) {
        node = document.createElement("div");
        node.className = className || "ledger-row";
        node.dataset.key = key;
        node.textContent = text;
        box.insertBefore(node, cursor);
      } else {
        if (node.textContent !== text) node.textContent = text;
        if (node !== cursor) box.insertBefore(node, cursor);
        else { cursor = node.nextSibling; continue; }
      }
      cursor = node.nextSibling;
    }
  }

  function renderUnifiedEvents(s) {
    const box = $("unifiedEventList");
    if (!box) return;
    const rows = (s.unifiedTimeline || []).slice()
      .sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)) || ((a.kind === "metric" ? 1 : 0) - (b.kind === "metric" ? 1 : 0)))
      .slice(-180);
    if (!rows.length) {
      if (box.textContent !== "Nenhum evento temporal capturado ainda.") {
        box.textContent = "Nenhum evento temporal capturado ainda.";
      }
      return;
    }
    reconcileKeyedRows(
      box,
      rows,
      (r, i) => r.id || r.eventId || `u_${r.kind || "e"}_${r.minute ?? "?"}_${r.extraMinute || 0}_${r.period || 0}_${r.side || r.team || ""}_${r.type || r.metric || ""}_${i}`,
      (r) => {
        const who = r.team || r.side || "—";
        if (r.kind === "metric") {
          return `${r.minute}${r.extraMinute ? `+${r.extraMinute}` : ""}' · ${r.period === 1 ? "1º" : "2º"}T · ${who} · ${METRIC_LABELS[r.metric] || r.metric} · ${r.from} → ${r.to}`;
        }
        return `${r.minute}${r.extraMinute ? `+${r.extraMinute}` : ""}' · ${r.period === 1 ? "1º" : "2º"}T · ${who} · ${r.type}${r.label ? ` · ${r.label}` : ""}`;
      },
      "ledger-row"
    );
  }

  function renderCornerContexts(s) {
    const box = $("cornerContextList");
    if (!box) return;
    const rows = (s.cornerContexts || []).slice().sort((a, b) => (a.period - b.period) || (a.minute - b.minute)).slice(-100);
    if (!rows.length) {
      if (box.textContent !== "Nenhum contexto de escanteio calculado ainda.") {
        box.textContent = "Nenhum contexto de escanteio calculado ainda.";
      }
      return;
    }
    reconcileKeyedRows(
      box,
      rows,
      (r, i) => r.id || `cc_${r.minute ?? "?"}_${r.extraMinute || 0}_${r.period || 0}_${r.side || r.team || ""}_${i}`,
      (r) => {
        const counts = Object.entries(r.prior10m || {}).filter(([, v]) => v > 0).map(([k, v]) => `${METRIC_LABELS[k] || k}: ${v}`).join(" · ");
        return `${r.minute}${r.extraMinute ? `+${r.extraMinute}` : ""}' · ${r.team || r.side} · Escanteio · últimos 10 min: ${counts || "nenhum evento detectado"}`;
      },
      "ledger-row"
    );
  }

  function renderLedger(s) {
    const box = $("statLedger");
    if (!box) return;
    const rows = Array.isArray(s.statChangeEvents)
      ? s.statChangeEvents.slice().sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)))
      : [];
    const frag = document.createDocumentFragment();
    rows.slice(-120).forEach(r => {
      const d = document.createElement("div");
      d.className = "ledger-row";
      d.textContent = `${r.minute}${r.extraMinute ? `+${r.extraMinute}` : ""}' · ${r.period === 1 ? "1º" : "2º"}T · ${r.team || r.side} · ${METRIC_LABELS[r.metric] || r.metric} · ${r.from} → ${r.to} (${r.delta > 0 ? "+" : ""}${r.delta})`;
      frag.appendChild(d);
    });
    if (!rows.length) {
      const d = document.createElement("div");
      d.textContent = "Nenhuma alteração histórica capturada ainda.";
      frag.appendChild(d);
    }
    box.innerHTML = "";
    box.appendChild(frag);
  }

  function renderHistory(s) {
    const svg = $("historySvg"), data = $("historyData");
    if (!svg || !data) return;
    svg.innerHTML = "";
    const metric = metricSelect ? metricSelect.value : "corners";
    const series = s.chartData?.teamSeries?.[metric] || { home: [], away: [] };
    const home = (series.home || []).filter(p => p?.value != null && Number.isFinite(Number(p.minute)) && Number(p.minute) >= 0 && Number(p.minute) <= 130);
    const away = (series.away || []).filter(p => p?.value != null && Number.isFinite(Number(p.minute)) && Number(p.minute) >= 0 && Number(p.minute) <= 130);
    const all = [...home, ...away];
    const W = 900, H = 300, L = 58, R = 22, T = 24, B = 48, gw = W - L - R, gh = H - T - B, ns = "http://www.w3.org/2000/svg";
    const maxMinute = Math.max(90, ...all.map(p => Number(p.minute) || 0), Number(s.minute) || 0);
    const maxVal = Math.max(1, ...all.map(p => Number(p.value) || 0), Number(s.stats?.[metric]?.home || 0), Number(s.stats?.[metric]?.away || 0));
    const line = (x1, y1, x2, y2, opacity = ".25") => {
      const e = document.createElementNS(ns, "line");
      e.setAttribute("x1", x1); e.setAttribute("y1", y1); e.setAttribute("x2", x2); e.setAttribute("y2", y2);
      e.setAttribute("stroke", "currentColor"); e.setAttribute("stroke-opacity", opacity);
      return e;
    };
    svg.appendChild(line(L, T, L, T + gh));
    svg.appendChild(line(L, T + gh, W - R, T + gh));
    for (let i = 0; i <= 6; i++) {
      const x = L + gw * i / 6;
      const e = document.createElementNS(ns, "text");
      e.setAttribute("x", x); e.setAttribute("y", H - 14); e.setAttribute("text-anchor", "middle");
      e.textContent = Math.round(maxMinute * i / 6) + "'";
      svg.appendChild(e);
    }
    for (let i = 0; i <= 5; i++) {
      const y = T + gh - gh * i / 5;
      const e = document.createElementNS(ns, "text");
      e.setAttribute("x", L - 8); e.setAttribute("y", y + 4); e.setAttribute("text-anchor", "end");
      e.textContent = (maxVal * i / 5).toFixed(metric === "xg" || metric === "possession" ? 1 : 0);
      svg.appendChild(e);
    }
    function plot(points, dash) {
      if (!points.length) return;
      const pts = points.map(p => [L + gw * ((Number(p.minute) || 0) + (Number(p.extraMinute) || 0) / 10) / maxMinute, T + gh - gh * (Number(p.value) || 0) / maxVal]);
      const poly = document.createElementNS(ns, "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", "currentColor");
      poly.setAttribute("stroke-width", "3");
      if (dash) poly.setAttribute("stroke-dasharray", "8 6");
      poly.setAttribute("points", pts.map(p => p.join(",")).join(" "));
      svg.appendChild(poly);
      pts.forEach((p, i) => {
        const c = document.createElementNS(ns, "circle");
        c.setAttribute("cx", p[0]); c.setAttribute("cy", p[1]); c.setAttribute("r", "4");
        c.setAttribute("fill", "currentColor");
        c.setAttribute("data-index", i);
        svg.appendChild(c);
      });
    }
    plot(home, false);
    plot(away, true);
    data.innerHTML = `<b>${s.home || "Casa"}</b>: ${(home || []).map(p => `${p.minute}${p.extraMinute ? `+${p.extraMinute}` : ""}'=${p.value}`).join(" · ") || "sem histórico"}<br><b>${s.away || "Visitante"}</b>: ${(away || []).map(p => `${p.minute}${p.extraMinute ? `+${p.extraMinute}` : ""}'=${p.value}`).join(" · ") || "sem histórico"}`;
  }

  function renderOdds(s) {
    const sum = $("oddsSummary"), box = $("oddsList");
    if (!sum || !box) return;
    const rows = (s.oddsHistory || []).slice().sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)) || (a.timestamp - b.timestamp));
    const sumText = `Cotações registradas: ${rows.length} · alterações: ${(s.oddsChanges || []).length} · mercados: ${Object.keys(s.oddsMarkets || {}).length}`;
    if (sum.textContent !== sumText) sum.textContent = sumText;
    const corner = rows.filter(r => r.marketType === "corners").slice(-160);
    const list = corner.length ? corner : rows.slice(-160);
    if (!list.length) {
      if (box.textContent !== "Nenhuma cotação capturada ainda.") {
        box.textContent = "Nenhuma cotação capturada ainda.";
      }
      return;
    }
    reconcileKeyedRows(
      box,
      list,
      (r, i) => r.id || r.quoteId || `od_${r.minute ?? "?"}_${r.extraMinute || 0}_${r.period || 0}_${r.marketType || ""}_${r.market || ""}_${r.line ?? ""}_${r.selection || ""}_${i}`,
      (r) => {
        const p = r.fairProbability != null ? ` · prob. ajustada ${(r.fairProbability * 100).toFixed(1)}%` : ` · prob. bruta ${((r.impliedProbability || 0) * 100).toFixed(1)}%`;
        const ov = r.marketOverround != null ? ` · overround ${(r.marketOverround * 100).toFixed(1)}%` : "";
        const oddsStr = (typeof r.odds === "number" ? r.odds.toFixed(2) : String(r.odds ?? "—"));
        return `${r.minute}${r.extraMinute ? `+${r.extraMinute}` : ""}' · ${r.period === 1 ? "1º" : "2º"}T · ${r.marketType} · ${r.market}${r.line ? ` ${r.line}` : ""} · ${r.selection} · ${oddsStr}${p}${ov}`;
      },
      "ledger-row"
    );
  }

  function renderCornerIndicators(s) {
    const sum = $("cornerIndicatorSummary"), box = $("cornerIndicatorHistory");
    if (!sum || !box) return;
    const rows = (s.chartData?.cornerIndicatorTimeline || s.cornerIndicatorTimeline || []).slice()
      .sort((a, b) => (a.period - b.period) || (a.minute - b.minute) || ((a.extraMinute || 0) - (b.extraMinute || 0)));
    if (!rows.length) {
      sum.textContent = "Nenhum indicador de pressão capturado ainda.";
      box.textContent = "";
      return;
    }
    const latest = rows[rows.length - 1];
    const f = v => v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(2);
    const pair = v => v ? `${f(v.home)} / ${f(v.away)}` : "—";
    const appm = latest.appm || {};
    sum.textContent = `Minuto ${latest.minute}${latest.extraMinute ? `+${latest.extraMinute}` : ""}' · Ataques perigosos: ${pair(latest.dangerous)} · APPM 5m: ${pair(appm["5m"])} · APPM 10m: ${pair(appm["10m"])} · Fonte: ${latest.source || "—"}`;
    const frag = document.createDocumentFragment();
    const clockMin = Number(s.minute);
    const hasClock = Number.isFinite(clockMin) && clockMin >= 0;
    rows.slice(-120).forEach(r => {
      const d = document.createElement("div");
      d.className = "ledger-row";
      const a = r.appm || {}, p = r.pressure || {};
      const ptxt = Object.entries(p).filter(([k, v]) => {
        const im = String(k).match(/(\d{1,2})-(\d{1,2})/);
        if (!im) return false;
        const start = Number(im[1]), end = Number(im[2]);
        const hh = Number(v?.home), aa = Number(v?.away);
        if (!Number.isFinite(hh) || !Number.isFinite(aa)) return false;
        if (hh === 0 && aa === 0) return false;
        if (hasClock && start > clockMin) return false;
        if (aa === 0 && hh >= 50 && hasClock && end > clockMin) return false;
        if (hasClock && start >= clockMin && ((hh === 0 && aa > 0) || (aa === 0 && hh > 0))) return false;
        return true;
      }).map(([k, v]) => `${k}: ${f(v.home)}%/${f(v.away)}%`).join(" · ");
      d.textContent = `${r.minute}${r.extraMinute ? `+${r.extraMinute}` : ""}' · Perigosos ${pair(r.dangerous)} · APPM 1m ${pair(a["1m"])} · 3m ${pair(a["3m"])} · 5m ${pair(a["5m"])} · 10m ${pair(a["10m"])}${ptxt ? ` · Pressão ${ptxt}` : ""}`;
      frag.appendChild(d);
    });
    box.innerHTML = "";
    box.appendChild(frag);
  }

  function renderIntelligence(s) {
    const i = s?.intelligence || {}, q = s?.quality || {}, p = i.sourceConsensus || {};
    setText("aiReady", `${Math.round(Number(i.readiness || 0))}/100`);
    setText("quality", `${Math.round(Number(q.score || 0))}/100`);
    setText("consensus", `${Math.round(Number(p.score || 0) * 100)}%`);
    setText("anomalies", String((i.anomalies || []).length));
    const insights = $("insights");
    if (insights) {
      const m = i.momentum || {};
      insights.innerHTML = `<div class="panel"><h2>Sinais derivados</h2><div class="insight-grid"><div><span>Momentum mandante</span><b>${Number(m.home || 0).toFixed(2)}</b></div><div><span>Momentum visitante</span><b>${Number(m.away || 0).toFixed(2)}</b></div><div><span>Fontes ativas</span><b>${(p.activeSources || []).join(" · ") || "—"}</b></div><div><span>Conflitos</span><b>${Number(p.conflicts || 0)}</b></div></div></div>`;
    }
  }

  function renderPrincipalOverview(s) {
    const box = $("liveOverview");
    if (!box) return;
    const live = s.liveStatus === "live", finished = s.liveStatus === "finished";
    const q = Number(s.quality?.score || 0), readiness = Number(s.intelligence?.readiness || 0);
    const age = s.lastUpdate ? Math.max(0, Date.now() - Number(s.lastUpdate)) : null;
    const fresh = age != null && age < 8000;
    const corners = Number(s.stats?.corners?.home || 0) + Number(s.stats?.corners?.away || 0);
    const dangerous = Number(s.stats?.dangerous?.home || 0) + Number(s.stats?.dangerous?.away || 0);
    const xgH = s.stats?.xg?.home, xgA = s.stats?.xg?.away;
    const xg = (xgH != null && xgA != null) ? Number(xgH) + Number(xgA) : null;
    const mode = live ? "AO VIVO" : finished ? "FINALIZADA" : "AGUARDANDO CONFIRMAÇÃO";
    const cls = live ? "live" : finished ? "finished" : "unknown";
    const statusText = live
      ? (fresh ? "Captura ativa · atualização recente" : "Captura ativa · aguardando atualização")
      : finished ? "Dados históricos · partida encerrada" : "Página aberta · aguardando confirmação do estado";
    box.innerHTML = `<div class="overview-card ${cls}">
   <div class="overview-top"><div><span class="overview-kicker">PAINEL PRINCIPAL</span><strong>${mode}</strong><small>${statusText}</small></div><div class="live-state"><i></i>${fresh ? "ONLINE" : "SEM SINAL RECENTE"}</div></div>
   <div class="overview-metrics">
    <div><span>ESCANTEIOS</span><b>${corners}</b><em>${s.stats?.corners?.home ?? "—"} × ${s.stats?.corners?.away ?? "—"}</em></div>
    <div><span>PRESSÃO</span><b>${dangerous}</b><em>${s.stats?.dangerous?.home ?? "—"} × ${s.stats?.dangerous?.away ?? "—"}</em></div>
    <div><span>xG TOTAL</span><b>${xg == null ? "—" : xg.toFixed(2)}</b><em>${xgH ?? "—"} × ${xgA ?? "—"}</em></div>
    <div><span>CONFIANÇA</span><b>${Math.round(q)}%</b><em>IA ${Math.round(readiness)}/100</em></div>
   </div>
   <div class="overview-bottom"><span>Fonte <b>${s.lastSnapshotSource || "—"}</b></span><span>Eventos <b>${s.cornerEventCount || 0}</b></span><span>Snapshots <b>${s.statTimeline?.length || 0}</b></span><span>Atualização <b>${age == null ? "—" : (age / 1000).toFixed(1) + "s"}</b></span></div>
 </div>`;
    const pill = $("modePill");
    if (pill) {
      pill.textContent = mode;
      pill.className = `pill mode-${cls}`;
    }
  }

  function renderPressureCandles(s) {
    const host = $("candlePanel");
    if (!host) return;
    const rows = (s.chartData?.cornerIndicatorTimeline || s.cornerIndicatorTimeline || []).slice().sort((a, b) => (Number(a.minute) || 0) - (Number(b.minute) || 0));
    const pts = [];
    const clockMinEarly = Number(s.minute);
    const hasClockEarly = Number.isFinite(clockMinEarly) && clockMinEarly >= 0;
    for (const r of rows) {
      const map = r.pressure && typeof r.pressure === "object" ? r.pressure : {};
      const keys = Object.keys(map).filter(k => /^\d{1,2}-\d{1,2}$/.test(k));
      if (keys.length) {
        for (const k of keys) {
          const cell = map[k];
          const h = Number(cell?.home), a = Number(cell?.away);
          const m = k.match(/(\d{1,2})-(\d{1,2})/);
          if (m && hasClockEarly && Number(m[1]) > clockMinEarly) continue;
          const mid = m ? (Number(m[1]) + Number(m[2])) / 2 : Number(r.minute) || 0;
          if (Number.isFinite(h) && Number.isFinite(a) && (h !== 0 || a !== 0)) pts.push({ minute: mid, home: h, away: a, interval: k });
        }
      } else {
        const h = Number(map.home), a = Number(map.away);
        if (Number.isFinite(h) && Number.isFinite(a) && (h !== 0 || a !== 0)) pts.push({ minute: Number(r.minute) || 0, home: h, away: a });
      }
    }
    const bars = s.charts?.pressureBars || {};
    const clockMin = Number(s.minute);
    const hasClock = Number.isFinite(clockMin) && clockMin >= 0;
    for (const [k, v] of Object.entries(bars)) {
      if (!v || v.empty) continue;
      const m = String(k).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
      if (!m) continue;
      const start = Number(m[1]), end = Number(m[2]);
      const mid = (start + end) / 2;
      if (hasClock && start > clockMin) continue;
      let h = Number(v.home), a = Number(v.away), pct = Number(v.pct);
      if (Number.isFinite(pct) && pct >= 0 && pct <= 100) {
        h = pct;
        a = Number((100 - pct).toFixed(1));
      } else if (Number.isFinite(h) && Number.isFinite(a) && h > 0 && a > 0 && (h > 100 || a > 100 || (h <= 1.5 && a <= 1.5))) {
        const ssum = h + a;
        h = Number(((h / ssum) * 100).toFixed(1));
        a = Number(((a / ssum) * 100).toFixed(1));
      }
      if (Number.isFinite(h) && Number.isFinite(a)) {
        if (h === 0 && a === 0) continue;
        if ((h === 0 && a > 0) || (a === 0 && h > 0)) continue;
        pts.push({ minute: mid, home: h, away: a, interval: m[1] + "-" + m[2] });
      }
    }
    const seen = new Set();
    const uniq = [];
    for (const p of pts.sort((a, b) => a.minute - b.minute)) {
      if (hasClock && p.interval) {
        const im = String(p.interval).match(/(\d{1,2})-(\d{1,2})/);
        if (im && Number(im[1]) > clockMin) continue;
      }
      const key = (p.interval || "") + ":" + p.minute + ":" + p.home + ":" + p.away;
      if (seen.has(key)) continue;
      seen.add(key);
      uniq.push(p);
    }
    const data = uniq.slice(-90);
    host.innerHTML = `<div class="chart-head"><div><span class="chart-kicker">MICROESTRUTURA DE PRESSÃO</span><h2>Velas de pressão · variação entre snapshots</h2><p>Velas derivadas exclusivamente dos pontos de pressão capturados. Corpo = abertura/fechamento; pavio = faixa observada entre snapshots.</p></div><div class="chart-live"><i></i> DADOS REAIS</div></div><div class="candle-legend"><span class="candle-home-key">● Mandante</span><span class="candle-away-key">● Visitante</span><span>▌ alta · ▐ baixa</span></div><div class="candle-stage"><svg id="pressureCandleSvg" viewBox="0 0 1100 360" preserveAspectRatio="none" role="img" aria-label="Velas de variação de pressão por minuto"></svg></div><div id="candleData" class="chart-foot"></div>`;
    const svg = document.getElementById("pressureCandleSvg"), ns = "http://www.w3.org/2000/svg";
    if (!svg) return;
    const W = 1100, H = 360, L = 58, R = 22, T = 24, B = 42, gw = W - L - R, gh = H - T - B;
    if (!data.length) {
      const cd = document.getElementById("candleData");
      if (cd) cd.textContent = "Nenhum ponto de pressão suficiente para construir velas.";
      return;
    }
    const vals = data.flatMap(r => [r.home, r.away]);
    let min = Math.min(0, ...vals), max = Math.max(100, ...vals);
    if (max - min < 10) {
      const mid = (max + min) / 2;
      min = Math.max(0, mid - 5);
      max = Math.min(100, mid + 5);
    }
    const line = (x1, y1, x2, y2, op) => {
      const e = document.createElementNS(ns, "line");
      Object.entries({ x1, y1, x2, y2, stroke: "currentColor", "stroke-opacity": op }).forEach(([k, v]) => e.setAttribute(k, v));
      return e;
    };
    for (let i = 0; i <= 5; i++) {
      const y = T + gh * i / 5;
      svg.appendChild(line(L, y, W - R, y, .22));
      const t = document.createElementNS(ns, "text");
      t.setAttribute("x", L - 8); t.setAttribute("y", y + 4); t.setAttribute("text-anchor", "end");
      t.textContent = (max - (max - min) * i / 5).toFixed(0) + "%";
      svg.appendChild(t);
    }
    const step = gw / Math.max(1, data.length - 1);
    function candle(side, cls, offset) {
      let prev = null;
      data.forEach((r, i) => {
        const v = side === "home" ? r.home : r.away;
        if (prev == null) { prev = v; return; }
        const open = prev, close = v, high = Math.max(open, close), low = Math.min(open, close), x = L + i * step + offset;
        const y = v => T + gh * (1 - (v - min) / (max - min));
        const wick = document.createElementNS(ns, "line");
        wick.setAttribute("x1", x); wick.setAttribute("x2", x); wick.setAttribute("y1", y(high)); wick.setAttribute("y2", y(low));
        wick.setAttribute("class", cls + " candle-wick");
        svg.appendChild(wick);
        const body = document.createElementNS(ns, "rect");
        body.setAttribute("x", x - 3.5); body.setAttribute("y", Math.min(y(open), y(close)));
        body.setAttribute("width", 7); body.setAttribute("height", Math.max(2, Math.abs(y(open) - y(close))));
        body.setAttribute("rx", 1); body.setAttribute("class", cls + " candle-body");
        svg.appendChild(body);
        prev = v;
      });
    }
    candle("home", "candle-home", -4);
    candle("away", "candle-away", 4);
    for (let i = 0; i < 6; i++) {
      const x = L + gw * i / 5;
      const t = document.createElementNS(ns, "text");
      t.setAttribute("x", x); t.setAttribute("y", H - 12); t.setAttribute("text-anchor", "middle");
      t.textContent = Math.round((Math.max(...data.map(r => r.minute)) / 5) * i) + "'";
      svg.appendChild(t);
    }
    const cd = document.getElementById("candleData");
    if (cd) {
      cd.innerHTML = `<span>Pontos: <b>${data.length}</b></span><span>Último: <b>${data.at(-1).home.toFixed(1)}% × ${data.at(-1).away.toFixed(1)}%</b></span><span>Interpretação: <b>variação de pressão entre snapshots</b></span>`;
    }
  }

  /* ───────────────────────── Batched Core Render (single RAF) ───────────────────────── */
  function performBatchedRender(s) {
    if (!s) return;

    // Prioridade conceitual (0 crítica → 2 normal): placar/minuto primeiro,
    // depois stats, depois listas históricas. Isolamento: falha em uma seção
    // não impede as demais (try/catch por bloco).
    const safe = (label, fn) => {
      try { fn(); } catch (err) { console.error("[CornerAI][dashboard] render fail:", label, err); }
    };

    safe("leds+core", () => {
      const age = Date.now() - (s.lastUpdate || 0);
      led("dom", Date.now() - (s.sources?.dom?.lastUpdate || 0) < 5000);
      led("hook", Date.now() - (s.sources?.hook?.lastUpdate || 0) < 7000);
      led("net", Date.now() - (s.sources?.network?.lastUpdate || 0) < 7000);

      setText("home", s.home || "--");
      setText("away", s.away || "--");
      setText("score", `${s.score?.home ?? 0} × ${s.score?.away ?? 0}`);
      setText("minute", s.minute == null ? "--" : `${s.minute}'`);
      const modeEl = $("mode");
      if (modeEl) modeEl.textContent = s.liveStatus === "finished" ? "HISTÓRICO" : s.liveStatus === "live" ? "AO VIVO" : String(s.dataMode || "AGUARDANDO").toUpperCase();
      setText("match", s.fixtureId ? `Fixture ${s.fixtureId}` : "Nenhuma partida");
      setText("age", (age / 1000).toFixed(1) + "s");
      setText("source", s.lastSnapshotSource || "--");
      setText("events", `${s.cornerEventCount || 0} cantos / ${s.snapshotCount || 0} snapshots`);

      setText("teamName-home", s.home || "CASA");
      setText("teamName-away", s.away || "VISITANTE");

      for (const side of ["home", "away"]) {
        for (const k of KEYS) {
          const val = s.teamData?.[side]?.stats?.[k] ?? s.stats?.[k]?.[side];
          setText(`${k}-${side}`, val == null ? "—" : String(val));
        }
      }
    });

    safe("liveCapture", () => renderLiveCapture(s));
    safe("health", () => renderHealth(s));
    safe("menuCapture", () => renderMenuCapture(s));
    safe("h2h", () => renderH2H(s));

    safe("cornerLists", () => {
      const he = escEvents(s.cornerEvents, "home");
      const ae = escEvents(s.cornerEvents, "away");
      renderList("cornerHome", "cornerHomeTitle", he);
      renderList("cornerAway", "cornerAwayTitle", ae);
    });
    safe("graph", () => renderGraph(s));
    safe("history", () => renderHistory(s));
    safe("ledger", () => renderLedger(s));
    safe("unifiedEvents", () => renderUnifiedEvents(s));
    safe("cornerContexts", () => renderCornerContexts(s));
    safe("odds", () => renderOdds(s));
    safe("cornerIndicators", () => renderCornerIndicators(s));
    safe("intelligence", () => renderIntelligence(s));
    safe("principalOverview", () => renderPrincipalOverview(s));
    safe("pressureCandles", () => renderPressureCandles(s));
  }

  /* ───────────────────────── Live capture actions ───────────────────────── */
  const liveNowBtn = $("liveCaptureNow");
  if (liveNowBtn) {
    liveNowBtn.onclick = async () => {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const tab = tabs.find(t => /^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(t.url || ""));
      const r = await chrome.runtime.sendMessage({ type: "ARM_ACTIVE_GAME", tabId: tab?.id });
      setText("liveCaptureSub", r?.ok ? "Captura sincronizada." : "Não foi possível sincronizar automaticamente.");
    };
  }
  const liveDiagBtn = $("liveCaptureDiagnose");
  if (liveDiagBtn) {
    liveDiagBtn.onclick = () => chrome.runtime.sendMessage({ type: "OPEN_DIAGNOSTICS_WINDOW" });
  }

  /* ───────────────────────── Message & Bootstrap ───────────────────────── */
  chrome.runtime.onMessage.addListener(m => {
    if (m.type === "STATE_UPDATE") scheduleUpdate(m.state);
  });

  // Live-sync watchdog: STATE_UPDATE can be missed when the dashboard window
  // is backgrounded or the service worker wakes/sleeps between emissions.
  // Poll the authoritative background state as a fallback so the UI never
  // depends on F5/reopening the dashboard to catch up.
  let __dashboardPollBusy = false;
  async function pollAuthoritativeState(){
    if(__dashboardPollBusy) return;
    __dashboardPollBusy = true;
    try{
      const r = await new Promise(resolve=>{
        try{
          chrome.runtime.sendMessage({type:"REQUEST_STATE"}, res=>{
            void chrome.runtime.lastError;
            resolve(res||null);
          });
        }catch{ resolve(null); }
      });
      if(r?.fixtureId || r?.lastUpdate || r?.stateVersion!=null) scheduleUpdate(r);
    }catch{}
    finally{ __dashboardPollBusy = false; }
  }
  pollAuthoritativeState();
  setInterval(pollAuthoritativeState, 1000);

  /* ───────────────────────── Visual Experience Layer (fully isolated) ───────────────────────── */
  (function visualExperience() {
    const nav = document.createElement("nav");
    nav.className = "visual-nav";
    nav.setAttribute("aria-label", "Navegação visual do dashboard");
    const navItems = [
      ["top", "Visão geral"], ["stats", "Estatísticas"], ["visualCharts", "Gráficos"],
      ["candlePanel", "Velas"], ["cornerGraph", "Escanteios"], ["oddsHistoryPanel", "Odds"],
      ["menuCapturePanel", "Menus"], ["healthPanel", "Saúde"]
    ];
    navItems.forEach(([id, label], i) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.dataset.target = id;
      if (i === 0) b.classList.add("active");
      b.addEventListener("click", () => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
        nav.querySelectorAll("button").forEach(x => x.classList.remove("active"));
        b.classList.add("active");
      });
      nav.appendChild(b);
    });
    const container = document.querySelector(".container");
    if (container) container.prepend(nav);

    const ribbon = document.createElement("div");
    ribbon.className = "freshness-ribbon";
    ribbon.id = "visualFreshness";
    ribbon.innerHTML = '<span><i class="status-dot"></i><strong>Estado da transmissão</strong></span><span id="visualFreshText">Aguardando dados</span>';
    if (container) container.insertBefore(ribbon, container.children[1]);

    const aiCard = document.createElement("section");
    aiCard.className = "ai-ready-card";
    aiCard.innerHTML = '<div><strong>Feed de IA preparado</strong><span>Pacote estruturado pronto para a futura Skill de análise ao vivo</span></div><b class="ai-ready-score" id="visualAiScore">—</b>';
    const overview = $("liveOverview");
    if (overview) overview.after(aiCard);

    // ── Gemini Skill Connector card (HTTP + WebSocket) ──
    const geminiCard = document.createElement("section");
    geminiCard.className = "panel gemini-skill-card";
    geminiCard.id = "geminiSkillPanel";
    geminiCard.innerHTML = `
      <span class="section-kicker">GEMINI CUSTOM SKILL</span>
      <h2>Skill Gemini · HTTP + WebSocket</h2>
      <p class="gemini-hint">HTTP one-shot ou stream WS em tempo real (auto-push a cada atualização de estado).</p>
      <div class="gemini-form">
        <label>URL do endpoint
          <input type="url" id="geminiEndpointUrl" placeholder="http://127.0.0.1:3000/experience" autocomplete="off" spellcheck="false">
        </label>
        <label>Gemini API Key (salva na extensão)
          <input type="password" id="geminiApiKey" placeholder="Cole a chave do Google AI Studio" autocomplete="off" spellcheck="false">
        </label>
        <div class="gemini-actions" style="margin-top:0">
          <button type="button" id="btnSaveGeminiKey" class="ai-send">Salvar API Key</button>
        </div>
        <div class="gemini-actions">
          <button type="button" id="btnExperienceV10" class="ai-send">Enviar → Experience :3000</button>
          <button type="button" id="btnGeminiV10" class="ghost">Analisar Gem API</button>
          <button type="button" id="btnGeminiPreview" class="ghost">Pré-visualizar</button>
          <button type="button" id="btnGeminiValidate" class="ghost">Validar payload</button>
          <button type="button" id="btnGeminiSync" class="ghost">POST URL</button>
          <button type="button" id="btnGeminiWsConnect" class="ghost" title="Somente receiver :8090">WS :8090</button>
          <button type="button" id="btnGeminiWsDisconnect" class="ghost">Stop WS</button>
        </div>
        <pre id="geminiV10Output" class="gemini-v10-output" hidden></pre>
        <div class="gemini-ws-line">
          <span class="ws-dot" id="geminiWsDot"></span>
          <span id="geminiWsLabel">Experience HTTP: —</span>
          <span id="geminiWsMeta" class="gemini-ws-meta"></span>
        </div>
        <div id="geminiStatus" class="gemini-status" aria-live="polite"></div>
      </div>
    `;
    if (aiCard && aiCard.parentNode) aiCard.after(geminiCard);

    (function bindGeminiSkill() {
      const btn = $("btnGeminiSync");
      const prev = $("btnGeminiPreview");
      const btnVal = $("btnGeminiValidate");
      const btnV10 = $("btnGeminiV10");
      const btnExp = $("btnExperienceV10");
      const outV10 = $("geminiV10Output");
      const btnWsOn = $("btnGeminiWsConnect");
      const btnWsOff = $("btnGeminiWsDisconnect");
      const statusEl = $("geminiStatus");
      const urlEl = $("geminiEndpointUrl");
      const keyEl = $("geminiApiKey");
      const dot = $("geminiWsDot");
      const label = $("geminiWsLabel");
      const meta = $("geminiWsMeta");
      if (!btn) return;

      try {
        chrome.storage.local.get(["cornerai_gemini_skill_url", "cornerai_gemini_skill_key", "cornerai_gemini", "cornerai_gemini_ws_url"], (r) => {
          if (urlEl) urlEl.value = r.cornerai_gemini_skill_url || "http://127.0.0.1:3000/experience";
          const savedKey = (r.cornerai_gemini && r.cornerai_gemini.apiKey) || r.cornerai_gemini_skill_key || "";
          if (keyEl && savedKey) keyEl.value = savedKey;
        });
      } catch {}

      function setStatus(msg, isErr) {
        if (!statusEl) return;
        statusEl.textContent = msg || "";
        statusEl.className = "gemini-status" + (isErr ? " err" : " ok");
      }

      function paintHttp(st) {
        if (!st) return;
        const online = !!st.online;
        if (dot) dot.className = "ws-dot " + (online ? "on" : "off");
        if (label) label.textContent = online ? "Experience HTTP: online" : "Experience HTTP: offline";
        if (meta) {
          const h = st.health || {};
          const parts = [];
          if (online) parts.push(":3000");
          if (h.matches != null) parts.push("hist " + h.matches);
          if (h.geminiConfigured != null) parts.push(h.geminiConfigured ? "gemini ok" : "sem key");
          if (st.error) parts.push(st.error);
          meta.textContent = parts.join(" · ");
        }
      }

      async function refreshHttpStatus() {
        try {
          const r = await chrome.runtime.sendMessage({
            type: "EXPERIENCE_HEALTH",
            baseUrl: "http://127.0.0.1:3000"
          });
          paintHttp(r || { online: false });
        } catch (e) {
          paintHttp({ online: false, error: String(e.message || e) });
        }
      }
      // Garante que nenhum WS fique em retry em background
      try { chrome.runtime.sendMessage({ type: "GEMINI_WS_DISCONNECT" }); } catch {}
      refreshHttpStatus();
      setInterval(refreshHttpStatus, 5000);

      async function persistCreds() {
        const key = (keyEl && keyEl.value || "").trim();
        const url = (urlEl && urlEl.value || "").trim();
        try {
          await chrome.storage.local.set({
            cornerai_gemini_skill_url: url,
            cornerai_gemini_ws_url: url,
            cornerai_gemini_skill_key: key
          });
        } catch {}
        // Salva também na config oficial AUTO-GEMINI (usada por RUN_GEMINI / RUN_GEMINI_V10)
        if (key) {
          try {
            await chrome.runtime.sendMessage({
              type: "SET_GEMINI",
              payload: { apiKey: key, enabled: true }
            });
          } catch {}
        }
      }

      const btnSaveKey = $("btnSaveGeminiKey");
      if (btnSaveKey) {
        btnSaveKey.onclick = async () => {
          const key = (keyEl && keyEl.value || "").trim();
          if (!key) {
            setStatus("Cole a Gemini API Key antes de salvar.", true);
            if (keyEl) keyEl.focus();
            return;
          }
          btnSaveKey.disabled = true;
          const old = btnSaveKey.textContent;
          btnSaveKey.textContent = "SALVANDO…";
          try {
            await persistCreds();
            const check = await chrome.storage.local.get(["cornerai_gemini"]);
            const ok = !!(check.cornerai_gemini && check.cornerai_gemini.apiKey);
            setStatus(ok ? "API Key salva nas configurações da extensão." : "Salvo (skill key).");
          } catch (e) {
            setStatus(String(e.message || e), true);
          }
          btnSaveKey.textContent = old;
          btnSaveKey.disabled = false;
        };
      }

            if (btnWsOn) {
        btnWsOn.onclick = async () => {
          const endpoint = (urlEl && urlEl.value || "").trim();
          if (!endpoint) {
            setStatus("Informe a URL (receiver :8090/ws ou Experience :3000 via botão dedicado).", true);
            return;
          }
          // Experience DB :3000 é HTTP-only — redireciona para POST
          const isExp = /:(3000)\b/.test(endpoint) || /\/api\/v10\//i.test(endpoint) || /\/experience\/?$/i.test(endpoint);
          if (isExp) {
            setStatus("URL :3000 é HTTP-only. Enviando via Experience DB (POST)…");
            if (btnExp) btnExp.click();
            else {
              try {
                const r = await chrome.runtime.sendMessage({
                  type: "RUN_EXPERIENCE_V10",
                  endpointUrl: endpoint.includes("/api/") || endpoint.includes("/experience")
                    ? endpoint
                    : "http://127.0.0.1:3000/api/v10/analyze"
                });
                if (r && r.ok) {
                  setStatus("Experience OK (HTTP) · sem WebSocket");
                  if (outV10) { outV10.hidden = false; outV10.textContent = JSON.stringify(r.decision != null ? r.decision : r, null, 2); }
                } else setStatus(r?.error || "Falha Experience HTTP", true);
              } catch (e) { setStatus(String(e.message || e), true); }
            }
            paintWs({ state: "closed", lastError: "http_only" });
            return;
          }
          btnWsOn.disabled = true;
          setStatus("Conectando WebSocket (receiver :8090)…");
          await persistCreds();
          try {
            const r = await chrome.runtime.sendMessage({
              type: "GEMINI_WS_CONNECT",
              url: endpoint,
              apiKey: (keyEl && keyEl.value || "").trim() || null
            });
            if (r && r.ok) {
              setStatus("WebSocket conectando/aberto — auto-push ativo.");
              paintWs(r.status || { state: "connecting" });
            } else {
              setStatus((r?.error || "Falha WS") + (r?.hint ? " — " + r.hint : ""), true);
              paintWs(r?.status || { state: "closed", lastError: r?.error });
            }
          } catch (e) {
            setStatus(String(e.message || e), true);
          }
          btnWsOn.disabled = false;
          setTimeout(refreshWsStatus, 600);
        };
      }

      if (btnWsOff) {
        btnWsOff.onclick = async () => {
          try {
            await chrome.runtime.sendMessage({ type: "GEMINI_WS_DISCONNECT" });
            setStatus("WebSocket desconectado.");
            paintWs({ state: "closed", sent: 0, recv: 0 });
          } catch (e) {
            setStatus(String(e.message || e), true);
          }
        };
      }

      if (prev) {
        prev.onclick = async () => {
          prev.disabled = true;
          setStatus("Gerando payload…");
          try {
            const r = await chrome.runtime.sendMessage({ type: "GEMINI_SYNC_REQUEST", forceHttp: true });
            if (r && r.ok && r.payload) {
              const pretty = JSON.stringify(r.payload, null, 2);
              try { await navigator.clipboard.writeText(pretty); } catch {}
              setStatus("Payload copiado (" + (r.payload.schemaVersion || "v1") + ").");
              console.log("[CornerAI Gemini payload]", r.payload);
            } else {
              setStatus(r?.error || "Falha ao gerar payload", true);
            }
          } catch (e) {
            setStatus(String(e.message || e), true);
          }
          prev.disabled = false;
        };
      }

      if (btnVal) {
        btnVal.onclick = async () => {
          btnVal.disabled = true;
          setStatus("Validando payload…");
          try {
            const r = await chrome.runtime.sendMessage({ type: "GEMINI_SYNC_REQUEST", forceHttp: true });
            if (!r || !r.ok || !r.payload) {
              setStatus(r?.error || "Falha ao gerar payload", true);
              btnVal.disabled = false;
              return;
            }
            const payload = r.payload;
            const localErrs = [];
            if (!payload.schemaVersion) localErrs.push("schemaVersion");
            if (!payload.matchContext) localErrs.push("matchContext");
            if (!payload.telemetryStats) localErrs.push("telemetryStats");
            const endpoint = (urlEl && urlEl.value || "").trim().replace(/\/gemini\/ws\/?$/, "/gemini/validate").replace(/\/gemini\/telemetry\/?$/, "/gemini/validate");
            let remote = null;
            if (endpoint && /\/gemini\/validate/.test(endpoint)) {
              try {
                const headers = { "Content-Type": "application/json" };
                const key = (keyEl && keyEl.value || "").trim();
                if (key) headers["Authorization"] = "Bearer " + key;
                const res = await fetch(endpoint, { method: "POST", headers, body: JSON.stringify(payload) });
                remote = await res.json().catch(() => ({ ok: false, error: "HTTP " + res.status }));
              } catch (e) {
                remote = { ok: false, error: String(e.message || e), note: "receiver offline?" };
              }
            }
            console.log("[CornerAI validate]", { localErrs, remote, payload });
            if (localErrs.length) {
              setStatus("Payload incompleto: " + localErrs.join(", "), true);
            } else if (remote && remote.ok === false && remote.error) {
              setStatus("Local OK · remoto: " + remote.error, true);
            } else if (remote && remote.ok === false && (remote.errors || []).length) {
              setStatus("Remoto: " + remote.errors.join("; "), true);
            } else if (remote && remote.ok) {
              const w = (remote.warnings || []).length;
              setStatus("Payload VÁLIDO" + (w ? " · " + w + " warning(s)" : "") + " · schema " + (remote.schema || payload.schemaVersion));
            } else {
              setStatus("Payload local OK (" + payload.schemaVersion + "). Suba o receiver p/ validar remoto.");
            }
          } catch (e) {
            setStatus(String(e.message || e), true);
          }
          btnVal.disabled = false;
        };
      }

            if (btnV10) {
        btnV10.onclick = async () => {
          btnV10.disabled = true;
          const old = btnV10.textContent;
          btnV10.textContent = "ANALISANDO…";
          setStatus("Consultando CornerAI v10 + Experience Database (API Gemini)…");
          if (outV10) { outV10.hidden = false; outV10.textContent = "…"; }
          try {
            const r = await chrome.runtime.sendMessage({ type: "RUN_GEMINI_V10" });
            console.log("[CornerAI Gem v10]", r);
            if (r && r.ok) {
              setStatus("Gem v10 OK · " + (r.model || "model") + (r.via ? " · " + r.via : ""));
              const pretty = typeof r.analysis === "string" ? r.analysis : JSON.stringify(r.analysis, null, 2);
              if (outV10) outV10.textContent = pretty;
              // Também grava no Experience DB local (HTTP)
              try {
                const exp = await chrome.runtime.sendMessage({
                  type: "RUN_EXPERIENCE_V10",
                  endpointUrl: "http://127.0.0.1:3000/experience"
                });
                if (exp && exp.ok) setStatus("Gem v10 OK · salvo no Experience (hist " + (exp.totalHistory != null ? exp.totalHistory : "?") + ")");
              } catch {}
            } else {
              setStatus(r?.error || "Falha Gem v10", true);
              if (outV10) outV10.textContent = r?.error || "erro";
            }
          } catch (e) {
            setStatus(String(e.message || e), true);
            if (outV10) outV10.textContent = String(e.message || e);
          }
          btnV10.textContent = old;
          btnV10.disabled = false;
        };
      }

            if (btnExp) {
        btnExp.onclick = async () => {
          btnExp.disabled = true;
          const oldTxt = btnExp.textContent;
          btnExp.textContent = "EXPERIENCE…";
          setStatus("Consultando Experience Database em :3000…");
          if (outV10) { outV10.hidden = false; outV10.textContent = "…"; }
          try {
            const r = await chrome.runtime.sendMessage({
              type: "RUN_EXPERIENCE_V10",
              endpointUrl: (urlEl && urlEl.value && /:3000/.test(urlEl.value) ? urlEl.value.trim() : "http://127.0.0.1:3000/experience")
            });
            console.log("[CornerAI Experience v10]", r);
            if (r && r.ok) {
              setStatus("Experience OK · histórico " + (r.totalHistory != null ? r.totalHistory : "?"));
              const pretty = JSON.stringify(r.decision != null ? r.decision : r, null, 2);
              if (outV10) outV10.textContent = pretty;
            } else {
              setStatus(r?.error || "Falha Experience :3000 (servidor ligado?)", true);
              if (outV10) outV10.textContent = r?.error || "erro";
            }
          } catch (e) {
            setStatus(String(e.message || e), true);
            if (outV10) outV10.textContent = String(e.message || e);
          }
          btnExp.textContent = oldTxt;
          btnExp.disabled = false;
        };
      }

            btn.onclick = async () => {
        const endpoint = (urlEl && urlEl.value || "").trim();
        if (!endpoint) {
          setStatus("Informe a URL do endpoint da Skill.", true);
          if (urlEl) urlEl.focus();
          return;
        }
        btn.disabled = true;
        const oldTxt = btn.textContent;
        btn.textContent = "ENVIANDO…";
        setStatus("Enviando HTTP…");
        await persistCreds();
        try {
          const r = await chrome.runtime.sendMessage({
            type: "GEMINI_SYNC_REQUEST",
            endpointUrl: endpoint.replace(/\/gemini\/ws\/?$/, "/gemini/telemetry"),
            apiKey: (keyEl && keyEl.value || "").trim() || null,
            forceHttp: true
          });
          if (r && r.ok) {
            btn.textContent = "ENVIADO ✓";
            setStatus("HTTP OK" + (r.via ? " (" + r.via + ")" : "") + ".");
            console.log("[CornerAI Gemini Skill result]", r.result);
          } else {
            btn.textContent = "ERRO";
            setStatus(r?.error || "Falha no envio", true);
          }
        } catch (e) {
          btn.textContent = "ERRO";
          setStatus(String(e.message || e), true);
        }
        setTimeout(() => {
          btn.textContent = oldTxt;
          btn.disabled = false;
        }, 2200);
      };
    })();

    const intel = document.createElement("section");
    intel.className = "panel";
    intel.id = "visualIntelligence";
    intel.innerHTML = '<span class="section-kicker">LEITURA VISUAL</span><h2>Momentum em tempo real</h2><div class="intelligence-visual"><div class="intel-card home"><span>Pressão mandante</span><b id="viHome">—</b><em>índice observado</em><div class="microbar"><i id="viHomeBar"></i></div></div><div class="intel-card away"><span>Pressão visitante</span><b id="viAway">—</b><em>índice observado</em><div class="microbar"><i id="viAwayBar"></i></div></div><div class="intel-card green"><span>Qualidade</span><b id="viQuality">—</b><em>confiabilidade do estado</em><div class="microbar"><i id="viQualityBar"></i></div></div><div class="intel-card gold"><span>Consenso</span><b id="viConsensus">—</b><em>convergência das fontes</em><div class="microbar"><i id="viConsensusBar"></i></div></div></div>';
    const statsEl = $("stats");
    if (statsEl) statsEl.before(intel);

    const events = document.createElement("section");
    events.className = "panel";
    events.id = "visualEvents";
    events.innerHTML = '<span class="section-kicker">⚽ EVENTOS</span><h2 title="🕒 Mostra os principais eventos em ordem de tempo">Linha do tempo visual <span class="help-icon" title="🕒 Exibe os eventos capturados na ordem em que aconteceram.">ⓘ</span></h2><div id="visualEventRail" class="event-rail"></div>';
    const live = $("liveOverview");
    if (live) live.after(events);

    function pct(v, max) {
      const n = Number(v);
      if (!Number.isFinite(n) || max <= 0) return 0;
      return Math.max(0, Math.min(100, n / max * 100));
    }

    function updateVisual(s) {
      if (!s) return;
      const q = Number(s.quality?.score || 0), ready = Number(s.intelligence?.readiness || 0), cons = Number(s.intelligence?.sourceConsensus?.score || 0) * 100;
      const m = s.intelligence?.momentum || {};
      const mh = Number(m.home || 0), ma = Number(m.away || 0);
      setText("viHome", mh.toFixed(2));
      setText("viAway", ma.toFixed(2));
      setText("viQuality", `${Math.round(q)}%`);
      setText("viConsensus", `${Math.round(cons)}%`);
      setText("visualAiScore", `${Math.round(ready)}/100`);
      const bar = (id, v, max) => {
        const e = $(id);
        if (e) e.style.width = `${pct(Math.abs(v), max)}%`;
      };
      bar("viHomeBar", mh, 1);
      bar("viAwayBar", ma, 1);
      bar("viQualityBar", q, 100);
      bar("viConsensusBar", cons, 100);
      const age = s.lastUpdate ? Math.max(0, Date.now() - Number(s.lastUpdate)) : Infinity;
      const rib = $("visualFreshness"), txt = $("visualFreshText");
      if (rib && txt) {
        const liveState = s.liveStatus === "live" && age < 10000;
        rib.classList.toggle("live", liveState);
        rib.classList.toggle("stale", s.liveStatus === "live" && !liveState);
        const dot = rib.querySelector(".status-dot");
        if (dot) dot.className = `status-dot ${liveState ? "live" : (s.liveStatus === "live" ? "warn" : "")}`;
        txt.textContent = age === Infinity ? "Aguardando primeira captura" : liveState ? `Online · atualizado há ${(age / 1000).toFixed(1)}s` : `Sem atualização recente · ${(age / 1000).toFixed(1)}s`;
      }
      const rail = $("visualEventRail");
      if (rail) {
        const ev = (Array.isArray(s.events) ? s.events : Array.isArray(s.cornerEvents) ? s.cornerEvents : [])
          .slice()
          .sort((a, b) => (Number(a.minute) || 0) - (Number(b.minute) || 0))
          .slice(-24);
        if (!ev.length) {
          if (rail.childElementCount !== 1 || !rail.firstChild?.classList?.contains("empty-visual")) {
            rail.innerHTML = '<div class="empty-visual">Nenhum evento observado ainda.</div>';
          }
        } else {
          // Reconciliação leve por chave no rail visual
          const wanted = new Map();
          ev.forEach((e, i) => {
            const key = e.id || e.eventId || `ve_${e.minute ?? "?"}_${e.extraMinute || 0}_${e.type || ""}_${i}`;
            const label = e.label || e.type || "Evento";
            const isCorner = String(e.type || "").toLowerCase().includes("corner");
            const isGoal = String(e.type || "").toLowerCase().includes("goal");
            wanted.set(key, { textB: `${e.minute ?? "—"}${e.extraMinute ? `+${e.extraMinute}` : ""}'`, textS: label, cls: `event-chip ${isCorner ? "corner" : ""} ${isGoal ? "goal" : ""}`.trim() });
          });
          const existing = new Map();
          Array.from(rail.children).forEach(node => {
            if (node.dataset?.key) existing.set(node.dataset.key, node);
          });
          for (const [k, node] of existing) {
            if (!wanted.has(k)) node.remove();
          }
          let cursor = rail.firstChild;
          for (const [key, info] of wanted) {
            let node = existing.get(key);
            if (!node) {
              node = document.createElement("div");
              node.dataset.key = key;
              node.className = info.cls;
              node.innerHTML = `<b></b><span></span>`;
              rail.insertBefore(node, cursor);
            } else if (node.className !== info.cls) {
              node.className = info.cls;
            }
            const b = node.querySelector("b");
            const sp = node.querySelector("span");
            if (b && b.textContent !== info.textB) b.textContent = info.textB;
            if (sp && sp.textContent !== info.textS) sp.textContent = info.textS;
            if (node !== cursor) rail.insertBefore(node, cursor);
            else { cursor = node.nextSibling; continue; }
            cursor = node.nextSibling;
          }
        }
      }
    }

    window.__corneraiVisualUpdate = updateVisual;

    const footer = document.querySelector("footer");
    if (footer) {
      const liveFoot = document.createElement("span");
      liveFoot.className = "footer-live";
      liveFoot.innerHTML = "<i></i>Interface visual "+((chrome.runtime.getManifest&&chrome.runtime.getManifest().version)||"12.6.17");
      footer.appendChild(liveFoot);
    }
  })();

  console.log("[CornerAI] Dashboard resilient architecture loaded · RAF single-flight · Validation gate active · v12.6.17");
})();

/* ───────── TTAdder / Extension NOC module ───────── */
(() => {
  "use strict";
  const q=[], samples=[], logs=[]; let processed=0, failed=0, total=0, lastCycle=Date.now(), windowKey="5m";
  const $=id=>document.getElementById(id);
  const set=(id,v)=>{const e=$(id);if(e)e.textContent=v};
  const esc=v=>String(v??"").replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]));
  function state(kind, age){const dot=$("ttStateDot"); if(dot)dot.className=kind==="live"?"live":kind==="warn"?"warn":kind==="err"?"err":""; set("ttState",kind==="live"?"LIVE":kind==="warn"?"DEGRADED":kind==="err"?"ERROR":"IDLE");set("ttStateAge",age!=null?`${(age/1000).toFixed(1)}s`:"—");}
  function draw(){const el=$("ttSpark");if(!el)return;const vals=samples.slice(-60), w=700,h=92,p=8; if(!vals.length){el.innerHTML="";return} const max=Math.max(1,...vals), min=Math.min(0,...vals), span=max-min||1; const pts=vals.map((v,i)=>`${p+(i/(Math.max(1,vals.length-1)))*(w-p*2)},${h-p-((v-min)/span)*(h-p*2)}`).join(" ");el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/><circle cx="${pts.split(" ").at(-1).split(",")[0]}" cy="${pts.split(" ").at(-1).split(",")[1]}" r="3" fill="currentColor"/></svg>`;}
  function log(type,status,payload){logs.unshift({time:new Date(),type,status,payload});logs.splice(24);const box=$("ttLogRows");if(!box)return;box.innerHTML=logs.map(x=>`<div class="tt-log-row"><span>${x.time.toLocaleTimeString("pt-BR",{hour12:false})}</span><span>${esc(x.type)}</span><span class="${x.status==="OK"?"tt-ok":x.status==="ERROR"?"tt-error":"tt-warn"}">${x.status}</span><span title="${esc(JSON.stringify(x.payload))}">${esc(JSON.stringify(x.payload))}</span></div>`).join("");set("ttLogStatus",`${logs.length} registros`);}
  function parsePayload(raw){const lines=String(raw||"").split(/\n+/).map(x=>x.trim()).filter(Boolean);const out=[];for(const line of lines){try{const v=JSON.parse(line);if(v&&typeof v==="object")out.push(v);else throw 0}catch{throw new Error(`JSON inválido na linha ${out.length+1}`)}}return out;}
  function preset(name){const map={corner:{fixtureId:$("fixture")?.textContent?.match(/\d+/)?.[0]||"",type:"corner",minute:Number($("minute")?.textContent?.match(/\d+/)?.[0]||0)},odds:{fixtureId:"",type:"odds",market:"corners",value:1.85,timestamp:Date.now()},metric:{fixtureId:"",type:"metric",name:"throughput",value:0,timestamp:Date.now()},batch:[{type:"corner",minute:82},{type:"corner",minute:86},{type:"odds",market:"over_10_5",value:1.72}]};$("ttPayload").value=JSON.stringify(map[name],null,2);}
  function validate(){try{const a=parsePayload($("ttPayload").value);set("ttCount",a.length);set("ttValid",a.length);log("validate","OK",{count:a.length});return a}catch(e){set("ttValid",0);log("validate","ERROR",{error:e.message});return null}}
  $("ttValidate")?.addEventListener("click",validate);
  $("ttClear")?.addEventListener("click",()=>{$("ttPayload").value="";set("ttCount",0);set("ttValid",0)});
  document.querySelectorAll("[data-tt-preset]").forEach(b=>b.addEventListener("click",()=>preset(b.dataset.ttPreset)));
  $("ttDryRun")?.addEventListener("change",e=>set("ttModeLabel",e.target.checked?"DRY-RUN":"LIVE"));
  $("ttAdd")?.addEventListener("click",()=>{const a=validate();if(!a)return;const dry=$("ttDryRun")?.checked!==false;a.forEach(x=>q.push(x));total+=a.length;set("ttQueue",q.length);log(dry?"dry-run":"enqueue","OK",{count:a.length,queue:q.length});set("ttToastText",dry?"Simulação validada — nenhum envio externo realizado":"Payloads adicionados à fila");});
  document.querySelectorAll("[data-tt-window]").forEach(b=>b.addEventListener("click",()=>{windowKey=b.dataset.ttWindow;document.querySelectorAll("[data-tt-window]").forEach(x=>x.classList.toggle("active",x===b));set("ttChartTitle",`Throughput · janela ${windowKey}`);draw()}));
  function ingest(s){
    if(!s)return;const now=Date.now(), age=s.lastUpdate?Math.max(0,now-Number(s.lastUpdate)):null;state(s.liveStatus==="live"&&age!=null&&age<10000?"live":s.liveStatus==="live"?"warn":"idle",age);
    const net=Number(s.diagnostics?.networkResponses||s.capture?.networkResponses||0), snaps=Number(s.snapshotCount||0);
    samples.push(Math.max(0,net));if(samples.length>240)samples.splice(0,samples.length-240);draw();
    set("ttDepth",String(s.capture?.outboxPending??s.outbox?.pending??0));set("ttClientLatency",age!=null?`${Math.round(age)}ms`:"—");set("ttServerLatency",s.diagnostics?.backgroundLatencyMs!=null?`${Math.round(s.diagnostics.backgroundLatencyMs)}ms`:"—");
    set("ttThroughput",`${net}/s`);set("ttRtt",age!=null?`${Math.round(age)}ms`:"—");set("ttRttSub",age!=null?"última atualização":"sem amostra");
    const errs=Number(s.diagnostics?.runtimeErrors||0)+Number(s.diagnostics?.networkFailures||0);set("ttErrorRate",`${Math.min(100,errs)}%`);set("ttErrorSub",errs?"falhas detectadas":"sem erros");
    const qd=Number(s.capture?.outboxPending??s.outbox?.pending??0);set("ttQueue",String(qd));set("ttProgressText",`${processed} processados · ${qd} na fila · ${failed} falhas · ETA —`);set("ttProgressBar",null);const bar=$("ttProgressBar");if(bar)bar.style.width=total?`${Math.min(100,processed/total*100)}%`:"0%";
  }
  chrome?.runtime?.onMessage?.addListener(msg=>{if(msg?.type==="STATE_UPDATE")ingest(msg.state);});
  try{chrome.runtime.sendMessage({type:"GET_CAPTURE_CONTEXT"},r=>{if(!chrome.runtime.lastError&&r)ingest(r.state||r)})}catch{}
  setInterval(()=>{if(q.length){const batch=q.splice(0,Math.min(25,q.length));processed+=batch.length;set("ttQueue",q.length);log("cycle","OK",{processed:batch.length,remaining:q.length});}draw()},1000);
  log("system","OK",{module:"TTAdder",mode:"dry-run",version:"12.6.17"});
})();
