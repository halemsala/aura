(() => {
if(window.__cornerAIChartsV69191)return;window.__cornerAIChartsV69191=true;
  "use strict";
  /**
   * CornerAI — Charts Unified Capture (SokkerPro)
   * Unifica 8 fontes visuais em um JSON normalizado:
   *  1) APPM / Pressão (3/5/10 min)
   *  2) xG cumulativo
   *  3) Timeline / carga de jogo (eventos)
   *  4) Oscilação de Odds
   *  5) MACD xG
   *  6) PBar (barra de pressão)
   *  7) H2H médias
   *  8) Radar / teia de estatísticas
   *
   * Arquitetura híbrida:
   *  - Network cache (page-hook → postMessage)
   *  - Chart.js / Highcharts / Vue / SVG DOM scrape
   *  - MutationObserver em abas Live/Gráficos (sem leak)
   *  - State hydration: campos ausentes ficam null + status pending|ready|stale
   */
  const VERSION="12.6.12";
  const PREFIX = "[CornerAI:Charts]";
  const MARK = "cornerai-page-hook";

  // ─── State ─────────────────────────────────────────────────────────
  const state = {
    matchId: null,
    liveTime: null,
    updatedAt: 0,
    sources: {},
    // caches
    netSeries: [],
    netPressure: {},
    netUrls: [],
    netAt: 0,
    netLabel: null,
    lastHash: "",
    lastEmit: 0,
    observer: null,
    tabObserver: null,
    pollTimer: null,
    armed: false
  };

  const clean = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
  const norm = (s) => clean(s).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const num = (v) => {
    const n = Number(String(v ?? "").replace(",", "."));
    return Number.isFinite(n) ? n : null;
  };

  function fixtureId() {
    try {
      if (typeof window.__corneraiNetFixture === "string" && /^\d{5,}$/.test(window.__corneraiNetFixture)) {
        return window.__corneraiNetFixture;
      }
    } catch {}
    try {
      const u = new URL(location.href);
      const q = u.searchParams.get("fixture") || u.searchParams.get("matchId");
      if (q && /^\d{5,}$/.test(q)) return q;
      const m = u.pathname.match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i);
      if (m) return m[1];
    } catch {}
    return null;
  }

  function liveClock() {
    try {
      const nodes = document.querySelectorAll(
        ".gs-live-min,.gs-match-min,.match-clock,.live-clock,[data-live-minute],[class*='live-min']"
      );
      for (const el of nodes) {
        const t = clean(el.textContent);
        const m = t.match(/^(\d{1,3})\s*\+\s*(\d{1,2})/) || t.match(/^(\d{1,3})\s*['′]?$/);
        if (m) {
          const minute = Number(m[1]);
          const extra = Number(m[2] || 0);
          if (minute >= 0 && minute <= 130) {
            return { minute, extraMinute: extra, display: extra ? `${minute}+${extra}'` : `${minute}'` };
          }
        }
      }
    } catch {}
    return null;
  }

  // ─── 1) APPM / Pressure intervals ──────────────────────────────────
  function extractAppm() {
    const out = { t3: {}, t5: {}, t10: {}, intervals: {}, source: null, status: "pending" };
    const blocks = document.querySelectorAll(
      "[class*='pressure'],[class*='appm'],[class*='ataque'],.pressure-block,.stat-pressure,[data-pressure]"
    );

    const ingestInterval = (key, home, away, src) => {
      const im = String(key).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
      if (!im) return;
      const start = Number(im[1]), end = Number(im[2]);
      const span = end - start;
      const h = num(home), a = num(away);
      if (h == null && a == null) return;
      const entry = { home: h, away: a, start, end, src };
      out.intervals[`${start}-${end}`] = entry;
      if (span <= 3) out.t3[`${start}-${end}`] = entry;
      else if (span <= 5) out.t5[`${start}-${end}`] = entry;
      else if (span <= 10) out.t10[`${start}-${end}`] = entry;
      out.source = out.source || src;
      out.status = "ready";
    };

    // From network cache
    for (const [k, v] of Object.entries(state.netPressure || {})) {
      if (v && (v.home != null || v.away != null)) ingestInterval(k, v.home, v.away, "network");
    }

    // DOM blocks
    for (const el of blocks) {
      const txt = clean(el.textContent || "").slice(0, 400);
      const im = txt.match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
      const nums = (txt.match(/\d+(?:[.,]\d+)?/g) || []).map((x) => Number(x.replace(",", ".")));
      if (im && nums.length >= 2) {
        // last two numbers often home/away or pct
        ingestInterval(im[0], nums[nums.length - 2], nums[nums.length - 1], "dom-block");
      }
    }

    // Text rows: "0-5  12  8"
    const lines = (document.body?.innerText || "").split(/\n/).map(clean).filter(Boolean);
    for (const line of lines.slice(0, 200)) {
      const im = line.match(/^(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(-?\d+(?:[.,]\d+)?)\s+(-?\d+(?:[.,]\d+)?)/);
      if (im) ingestInterval(`${im[1]}-${im[2]}`, im[3], im[4], "dom-text");
    }

    if (out.status === "pending" && Object.keys(out.intervals).length) out.status = "ready";
    return out;
  }

  // ─── 2) xG series ──────────────────────────────────────────────────
  function extractXgSeries(allSeries) {
    const home = [], away = [], values = [];
    const isXgName = (n) => /xg|expected\s*goals|gols?\s*esperados/i.test(String(n || ""));
    for (const p of allSeries || []) {
      const name = String(p.series || p.name || p.team || "");
      const minute = Number(p.minute ?? p.x ?? p.t);
      if (!Number.isFinite(minute) || minute < 0 || minute > 130) continue;
      if (p.home != null || p.away != null) {
        if (isXgName(name) || p.src === "chartjs" || !name) {
          home.push({ minute, value: num(p.home) });
          away.push({ minute, value: num(p.away) });
        }
      } else if (Number.isFinite(Number(p.value))) {
        if (isXgName(name) || /home|casa|mandante/i.test(name)) {
          home.push({ minute, value: Number(p.value) });
        } else if (/away|fora|visitante/i.test(name)) {
          away.push({ minute, value: Number(p.value) });
        } else if (isXgName(name)) {
          values.push({ minute, value: Number(p.value), series: name });
        }
      }
    }
    // DOM numeric xG pair
    let live = null;
    try {
      const rows = document.querySelectorAll(".stat-values-row,.statistics-row,tr.stat-row,[data-stat]");
      for (const row of rows) {
        const label = clean(row.querySelector(".stat-label,th,td:first-child")?.textContent || row.textContent || "");
        if (!/^xG\b|expected goals|gols esperados/i.test(label) && !/\bxg\b/i.test(label)) continue;
        const nums = (clean(row.textContent).match(/\d+(?:[.,]\d+)?/g) || []).map((x) => Number(x.replace(",", ".")));
        if (nums.length >= 2) live = { home: nums[0], away: nums[nums.length - 1] };
      }
    } catch {}
    const status = home.length || away.length || live ? "ready" : "pending";
    return { home, away, values, live, status, source: home.length ? "series" : live ? "dom" : null };
  }

  // ─── 3) Timeline / carga de jogo ───────────────────────────────────
  function extractTimeline() {
    const events = [];
    const seen = new Set();
    const push = (e) => {
      const key = `${e.minute}|${e.type}|${e.side || ""}|${e.label || ""}`;
      if (seen.has(key)) return;
      seen.add(key);
      events.push(e);
    };

    // Explicit event nodes
    for (const el of document.querySelectorAll(
      "[class*='incident'],[class*='event-item'],[class*='timeline'] li,[class*='match-event'],.event-row"
    )) {
      const t = clean(el.textContent || "");
      const mm = t.match(/(\d{1,3})(?:\+(\d{1,2}))?\s*['′]/);
      if (!mm) continue;
      const minute = Number(mm[1]);
      const extra = Number(mm[2] || 0);
      let type = "unknown";
      if (/escanteio|corner|canto/i.test(t)) type = "corner";
      else if (/gol|goal|score/i.test(t)) type = "goal";
      else if (/amarelo|yellow/i.test(t)) type = "yellow";
      else if (/vermelho|red card|expuls/i.test(t)) type = "red";
      else if (/falta|foul/i.test(t)) type = "foul";
      else if (/substitui|sub\b/i.test(t)) type = "substitution";
      else if (/impedimento|offside/i.test(t)) type = "offside";
      push({
        minute,
        extraMinute: extra,
        type,
        label: t.slice(0, 120),
        side: /casa|home|mandante/i.test(t) ? "home" : /fora|away|visitante/i.test(t) ? "away" : null,
        src: "dom-event"
      });
    }

    // Text timeline fallback
    if (events.length < 3) {
      const text = String(document.body?.innerText || "").slice(0, 25000);
      const re = /(\d{1,3})(?:\+(\d{1,2}))?['′]\s*([^\n\r]{3,80})/g;
      let m;
      while ((m = re.exec(text)) && events.length < 80) {
        const label = clean(m[3]);
        let type = null;
        if (/escanteio|corner/i.test(label)) type = "corner";
        else if (/\bgol\b|\bgoal\b/i.test(label)) type = "goal";
        else if (/amarelo|yellow/i.test(label)) type = "yellow";
        else if (/vermelho|red/i.test(label)) type = "red";
        else if (/falta|foul/i.test(label)) type = "foul";
        else if (/substitui/i.test(label)) type = "substitution";
        if (!type) continue;
        push({
          minute: Number(m[1]),
          extraMinute: Number(m[2] || 0),
          type,
          label: label.slice(0, 120),
          side: null,
          src: "dom-text"
        });
      }
    }

    events.sort((a, b) => a.minute - b.minute || (a.extraMinute || 0) - (b.extraMinute || 0));
    return {
      events: events.slice(0, 120),
      counts: {
        corner: events.filter((e) => e.type === "corner").length,
        goal: events.filter((e) => e.type === "goal").length,
        yellow: events.filter((e) => e.type === "yellow").length,
        red: events.filter((e) => e.type === "red").length,
        foul: events.filter((e) => e.type === "foul").length
      },
      status: events.length ? "ready" : "pending"
    };
  }

  // ─── 4) Odds oscillation ───────────────────────────────────────────
  function extractOddsOscillation() {
    const quotes = [];
    const seen = new Set();
    for (const el of document.querySelectorAll(
      "[class*='odd'],[class*='quota'],[class*='price'],[data-odd],[data-odds]"
    )) {
      const t = clean(el.textContent || "");
      const m = t.match(/(\d+[.,]\d{2,3})/);
      if (!m) continue;
      const odd = Number(m[1].replace(",", "."));
      if (!(odd >= 1.01 && odd <= 100)) continue;
      const key = t.slice(0, 40) + "|" + odd;
      if (seen.has(key)) continue;
      seen.add(key);
      quotes.push({
        label: t.slice(0, 80),
        odds: odd,
        implied: Number((1 / odd).toFixed(4)),
        src: "dom"
      });
    }
    // Detect drop: compare with previous snapshot on window
    let drops = [];
    try {
      const prev = window.__corneraiLastOddsSnap || [];
      if (prev.length && quotes.length) {
        for (const q of quotes.slice(0, 30)) {
          const p = prev.find((x) => x.label === q.label);
          if (p && p.odds > q.odds && (p.odds - q.odds) / p.odds >= 0.03) {
            drops.push({
              label: q.label,
              from: p.odds,
              to: q.odds,
              dropPct: Number((((p.odds - q.odds) / p.odds) * 100).toFixed(2))
            });
          }
        }
      }
      window.__corneraiLastOddsSnap = quotes.slice(0, 40);
    } catch {}
    return {
      quotes: quotes.slice(0, 40),
      drops,
      status: quotes.length ? "ready" : "pending"
    };
  }

  // ─── 5) MACD xG ────────────────────────────────────────────────────
  function extractMacdXg(allSeries) {
    const values = [];
    for (const p of allSeries || []) {
      const name = String(p.series || "");
      const minute = Number(p.minute ?? p.x);
      const value = Number(p.value ?? p.y);
      if (!Number.isFinite(minute) || minute < 0 || minute > 130) continue;
      if (!Number.isFinite(value)) continue;
      if (/macd|signal|hist|diverg/i.test(name) || p.src === "svg-poly" || p.src === "svg-path") {
        values.push({ minute, value, series: name || "macd", src: p.src || "series" });
      }
    }
    // Active tab signal
    const panel = clean(document.body?.innerText || "").slice(0, 3000);
    const active =
      /macd\s*xg/i.test(panel) ||
      !!document.querySelector(".macd-wrapper,.macd-faixa,.macd-head,[class*='macd']");
    return {
      values: values.slice(0, 300),
      active,
      status: values.length || active ? (values.length ? "ready" : "pending") : "pending",
      source: values.length ? "series" : active ? "tab-visible" : null
    };
  }

  // ─── 6) PBar ───────────────────────────────────────────────────────
  function extractPBar() {
    let homePercent = null,
      awayPercent = null,
      src = null;

    // Network pressure latest interval near current minute
    const clock = liveClock();
    const intervals = Object.entries(state.netPressure || {});
    if (intervals.length) {
      let best = null;
      for (const [k, v] of intervals) {
        const im = String(k).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
        if (!im || !v) continue;
        const mid = (Number(im[1]) + Number(im[2])) / 2;
        const h = num(v.home),
          a = num(v.away);
        if (h == null && a == null) continue;
        // Prefer pct-like 0-100
        let hp = h,
          ap = a;
        if (h != null && a != null && h + a > 0 && (h + a < 2 || h > 100 || a > 100)) {
          /* raw counts — convert */
          if (h <= 1.5 && a <= 1.5) {
            hp = h * 100;
            ap = a * 100;
          } else {
            const s = h + a;
            hp = (h / s) * 100;
            ap = (a / s) * 100;
          }
        }
        const dist = clock ? Math.abs(mid - clock.minute) : 0;
        if (!best || dist < best.dist) best = { hp, ap, dist, k };
      }
      if (best) {
        homePercent = Number(Number(best.hp).toFixed(1));
        awayPercent = Number(Number(best.ap).toFixed(1));
        src = "network-pressure";
      }
    }

    // DOM progress bars
    if (homePercent == null) {
      const bars = document.querySelectorAll(
        "[class*='pressure'] [style*='width'],[class*='pbar'] [style*='width'],.pressure-bar [style*='width']"
      );
      const widths = [];
      for (const el of bars) {
        const m = String(el.getAttribute("style") || "").match(/width\s*:\s*([\d.]+)\s*%/i);
        if (m) widths.push(Number(m[1]));
      }
      if (widths.length >= 2) {
        homePercent = widths[0];
        awayPercent = widths[1];
        src = "dom-width";
      } else if (widths.length === 1) {
        homePercent = widths[0];
        awayPercent = Number((100 - widths[0]).toFixed(1));
        src = "dom-width-single";
      }
    }

    // Text "Pressão 58% 42%"
    if (homePercent == null) {
      const body = (document.body?.innerText || "").slice(0, 5000);
      const m = body.match(/press[aã]o[^\n]{0,40}?(\d{1,3})\s*%[^\n]{0,20}?(\d{1,3})\s*%/i);
      if (m) {
        homePercent = Number(m[1]);
        awayPercent = Number(m[2]);
        src = "dom-text";
      }
    }

    return {
      homePercent,
      awayPercent,
      source: src,
      status: homePercent != null || awayPercent != null ? "ready" : "pending"
    };
  }

  // ─── 7) H2H ────────────────────────────────────────────────────────
  function extractH2h() {
    // Reuse payload from h2h-capture if present on window via last state
    let averages = null,
      summary = null,
      matches = 0;
    try {
      const st = window.__corneraiLatestState?.h2h;
      if (st) {
        averages = st.averages || null;
        summary = st.summary || null;
        matches = Array.isArray(st.matches) ? st.matches.length : Number(st.rows?.length || 0);
      }
    } catch {}

    // Lightweight DOM scrape
    if (!averages) {
      averages = {};
      const text = (document.body?.innerText || "").slice(0, 15000);
      const push = (key, a, b) => {
        averages[key] = { home: num(a), away: num(b) };
      };
      let m;
      const re =
        /(m[eé]dia\s+de\s+gols|escanteios?|corners?|cart[oõ]es?|chutes?|shots?)\s*[:=\-]?\s*(-?\d+(?:[.,]\d+)?)\s+(-?\d+(?:[.,]\d+)?)/gi;
      while ((m = re.exec(text))) {
        const lab = norm(m[1]);
        if (/gol|goal/.test(lab)) push("goals", m[2], m[3]);
        else if (/escante|corner/.test(lab)) push("corners", m[2], m[3]);
        else if (/cart/.test(lab)) push("cards", m[2], m[3]);
        else if (/chute|shot/.test(lab)) push("shots", m[2], m[3]);
      }
    }

    const status =
      (averages && Object.keys(averages).length) || summary || matches ? "ready" : "pending";
    return { averages, summary, matches, status };
  }

  // ─── 8) Radar / teia ───────────────────────────────────────────────
  function extractRadar() {
    const axes = [];
    const homeStats = [];
    const awayStats = [];

    // SVG polygon points (radar charts)
    try {
      const polys = document.querySelectorAll(
        "svg polygon, svg polyline, [class*='radar'] polygon, [class*='spider'] polygon"
      );
      for (const poly of polys) {
        const pts = String(poly.getAttribute("points") || "")
          .trim()
          .split(/[\s,]+/)
          .map(Number)
          .filter(Number.isFinite);
        if (pts.length >= 6) {
          axes.push({ points: pts.slice(0, 24), src: "svg-polygon" });
        }
      }
    } catch {}

    // Stat rows as radar axes
    const labels = {
      possession: /posse|possession/i,
      shots: /chute|shot|finaliza/i,
      shotsOn: /no alvo|a gol|on target/i,
      attacks: /ataques?(?!\s*perigos)/i,
      dangerous: /perigoso|dangerous/i,
      corners: /escanteio|corner/i,
      fouls: /falta|foul/i,
      passes: /passe/i
    };
    for (const row of document.querySelectorAll(
      ".stat-values-row,.statistics-row,tr.stat-row,[data-stat],.stat-item"
    )) {
      const label = clean(
        row.querySelector(".stat-label,th,td:first-child")?.textContent || row.textContent || ""
      ).slice(0, 60);
      const nums = (clean(row.textContent).match(/\d+(?:[.,]\d+)?/g) || []).map((x) =>
        Number(x.replace(",", "."))
      );
      if (nums.length < 2) continue;
      for (const [key, rx] of Object.entries(labels)) {
        if (rx.test(label)) {
          homeStats.push({ key, label, value: nums[0] });
          awayStats.push({ key, label, value: nums[nums.length - 1] });
          break;
        }
      }
    }

    return {
      axes,
      homeStats,
      awayStats,
      status: homeStats.length || axes.length ? "ready" : "pending"
    };
  }

  // ─── Series aggregation (Chart.js / Highcharts / SVG / net) ────────
  function scrapeLibrarySeries() {
    const series = [];
    const push = (p) => {
      if (!p) return;
      if (Number.isFinite(p.value) || Number.isFinite(p.home) || Number.isFinite(p.away)) series.push(p);
    };

    // Chart.js
    try {
      const ChartApi = window.Chart || window.ChartJS;
      for (const c of document.querySelectorAll("canvas")) {
        let ch = null;
        try {
          if (ChartApi?.getChart) ch = ChartApi.getChart(c);
        } catch {}
        if (!ch) try {
          ch = c.__chartjs__ || c.chart || c._chart;
        } catch {}
        if (!ch?.data) continue;
        const labels = ch.data.labels || [];
        (ch.data.datasets || []).forEach((d, di) => {
          const name = clean(d.label || "dataset-" + di);
          (d.data || []).forEach((v, i) => {
            let minute = null,
              value = null,
              home = null,
              away = null;
            if (v != null && typeof v === "object") {
              minute = Number(v.x ?? v.minute ?? labels[i]);
              value = Number(v.y ?? v.value);
              home = num(v.home);
              away = num(v.away);
            } else {
              minute = Number(labels[i] ?? i);
              value = Number(v);
            }
            if (Number.isFinite(value))
              push({ minute: Number.isFinite(minute) ? minute : i, value, series: name, src: "chartjs" });
            else if (home != null || away != null)
              push({
                minute: Number.isFinite(minute) ? minute : i,
                home,
                away,
                series: name,
                src: "chartjs"
              });
          });
        });
      }
    } catch {}

    // Highcharts
    try {
      const charts = window.Highcharts?.charts || [];
      for (const ch of charts) {
        if (!ch) continue;
        for (const s of ch.series || []) {
          const name = clean(s.name || "");
          for (const pt of s.data || s.points || []) {
            const minute = Number(pt.x ?? pt.category ?? pt.name);
            const value = Number(pt.y ?? pt.value);
            if (Number.isFinite(minute) && Number.isFinite(value))
              push({ minute, value, series: name, src: "highcharts" });
          }
        }
      }
    } catch {}

    // Network cache
    for (const p of state.netSeries || []) push({ ...p, src: p.src || "network" });

    return series.slice(0, 800);
  }

  // ─── Unified build ─────────────────────────────────────────────────
  function buildUnified() {
    const clock = liveClock();
    const allSeries = scrapeLibrarySeries();
    const appm = extractAppm();
    const xg = extractXgSeries(allSeries);
    const timeline = extractTimeline();
    const odds = extractOddsOscillation();
    const macdXg = extractMacdXg(allSeries);
    const pbar = extractPBar();
    const h2h = extractH2h();
    const radar = extractRadar();

    const readiness = {
      appm: appm.status,
      xg: xg.status,
      timeline: timeline.status,
      odds: odds.status,
      macdXg: macdXg.status,
      pbar: pbar.status,
      h2h: h2h.status,
      radar: radar.status
    };
    const readyCount = Object.values(readiness).filter((s) => s === "ready").length;

    const pack = {
      schema: "cornerai-charts-unified-1",
      version: VERSION,
      matchId: fixtureId() || state.matchId || null,
      liveTime: clock?.display || state.liveTime || null,
      minute: clock?.minute ?? null,
      extraMinute: clock?.extraMinute ?? 0,
      updatedAt: Date.now(),
      readiness,
      readyCount,
      hydration: readyCount >= 3 ? "hydrated" : readyCount >= 1 ? "partial" : "empty",
      // 1
      appm: {
        t3: appm.t3,
        t5: appm.t5,
        t10: appm.t10,
        intervals: appm.intervals,
        status: appm.status,
        source: appm.source
      },
      // 2
      xg: {
        home: xg.home,
        away: xg.away,
        values: xg.values,
        live: xg.live,
        status: xg.status
      },
      // 3
      timeline: {
        events: timeline.events,
        counts: timeline.counts,
        status: timeline.status
      },
      // 4
      oddsOscillation: {
        quotes: odds.quotes,
        drops: odds.drops,
        status: odds.status
      },
      // 5
      macdXg: {
        values: macdXg.values,
        active: macdXg.active,
        status: macdXg.status
      },
      // 6
      pbar: {
        homePercent: pbar.homePercent,
        awayPercent: pbar.awayPercent,
        status: pbar.status,
        source: pbar.source
      },
      // 7
      h2h: {
        averages: h2h.averages,
        summary: h2h.summary,
        matches: h2h.matches,
        status: h2h.status
      },
      // 8
      radar: {
        homeStats: radar.homeStats,
        awayStats: radar.awayStats,
        axes: radar.axes,
        status: radar.status
      },
      // meta
      seriesCount: allSeries.length,
      networkAt: state.netAt || 0,
      networkUrls: state.netUrls.slice(0, 8),
      // explicit signals for diagnostics (never leave sources empty when data exists)
      signals: (function(){
        const sources = [];
        if (appm.status === "ready" || Object.keys(appm.intervals||{}).length) sources.push("pressure-block");
        if (xg.status === "ready" || (xg.values&&xg.values.length)) sources.push("xg");
        if (macdXg.status === "ready" || (macdXg.values&&macdXg.values.length)) sources.push("macd_xg");
        if (pbar.status === "ready") sources.push("pressure_bar");
        if (timeline.status === "ready" || (timeline.events&&timeline.events.length)) sources.push("timeline");
        if (odds.status === "ready") sources.push("odds");
        if (h2h.status === "ready") sources.push("h2h");
        if (radar.status === "ready") sources.push("radar");
        if ((state.netSeries||[]).length) sources.push("network");
        return {
          hasMacd: macdXg.status === "ready" || !!(macdXg.values&&macdXg.values.length),
          hasAi: readyCount >= 2,
          sources: [...new Set(sources)],
          readyCount
        };
      })()
    };

    state.matchId = pack.matchId;
    state.liveTime = pack.liveTime;
    state.updatedAt = pack.updatedAt;
    return pack;
  }

  // ─── Emit to background (coalesced) ────────────────────────────────
  function emit(force = false) {
    if (!state.armed && !force) return null;
    const pack = buildUnified();
    const hash = JSON.stringify({
      r: pack.readiness,
      p: pack.pbar,
      xc: pack.xg.live,
      mc: pack.macdXg.values.length,
      tc: pack.timeline.events.length,
      ac: Object.keys(pack.appm.intervals || {}).length
    });
    const now = Date.now();
    if (!force && hash === state.lastHash && now - state.lastEmit < 2000) return pack;
    state.lastHash = hash;
    state.lastEmit = now;
    try {
      chrome.runtime.sendMessage(
        { type: "CHARTS_UNIFIED", payload: pack },
        () => {
          void chrome.runtime.lastError;
        }
      );
    } catch {}
    try {
      window.__corneraiChartsUnified = pack;
    } catch {}
    return pack;
  }

  // ─── Network bridge from page-hook ─────────────────────────────────
  window.addEventListener("message", (e) => {
    try {
      if (e.source !== window || e.origin !== location.origin) return;
      if (e.data?.source !== MARK) return;
      if (e.data?.type !== "NETWORK_PAYLOAD" && e.data?.type !== "CHART_SERIES") return;
      const p = e.data.payload;
      if (!p || p.hookTest) return;
      if (Array.isArray(p.series) && p.series.length) {
        state.netSeries = [...state.netSeries, ...p.series].slice(-800);
      }
      if (p.pressureBars && typeof p.pressureBars === "object") {
        state.netPressure = { ...state.netPressure, ...p.pressureBars };
      }
      if (p.__endpoint || p.url) {
        const u = String(p.__endpoint || p.url);
        if (!state.netUrls.includes(u)) state.netUrls = [...state.netUrls, u].slice(-12);
      }
      if (p.activeLabel) state.netLabel = String(p.activeLabel);
      state.netAt = Date.now();
      // Soft emit on network chart data
      if (state.armed) {
        clearTimeout(state._netEmit);
        state._netEmit = setTimeout(() => emit(false), 400);
      }
    } catch {}
  });

  // ─── MutationObserver (tabs Live / Gráficos) ───────────────────────
  function findChartRoot() {
    const el = document.querySelector('.macd-wrapper,.pressure-grid,#line-chart,canvas#line-chart,[class*="chart"],[class*="macd"],[class*="pressure"]');
    if (!el) return null;
    return el.tagName === 'CANVAS' ? (el.parentElement || el) : el;
  }

  function installTabObserver() {
    if (state.tabObserver) return;
    let debounce = null;
    const bind = () => {
      const root = findChartRoot();
      if (!root) return false;
      try { state.tabObserver.disconnect(); } catch {}
      try {
        state.tabObserver.observe(root, { childList: true, subtree: true, attributes: false, characterData: false });
        return true;
      } catch { return false; }
    };
    state.tabObserver = new MutationObserver(() => {
      clearTimeout(debounce);
      debounce = setTimeout(() => { if (state.armed) emit(false); }, 350);
    });
    if (!bind()) {
      setTimeout(bind, 1000);
      setTimeout(bind, 4000);
    }
  }

  function arm() {
    state.armed = true;
    installTabObserver();
    emit(true);
    clearInterval(state.pollTimer);
    // Poll leve: hidratação gradual de gráficos ainda não montados
    state.pollTimer = setInterval(() => {
      if (!state.armed) return;
      emit(false);
    }, 4000);
  }

  function disarm() {
    state.armed = false;
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  // ─── Messaging ─────────────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (!msg?.type) return;
    if (msg.type === "CHARTS_UNIFIED_ARM") {
      arm();
      sendResponse({ ok: true, pack: window.__corneraiChartsUnified || null });
      return true;
    }
    if (msg.type === "CHARTS_UNIFIED_DISARM") {
      disarm();
      sendResponse({ ok: true });
      return true;
    }
    if (msg.type === "CHARTS_UNIFIED_GET") {
      const pack = buildUnified();
      sendResponse({ ok: true, pack });
      return true;
    }
    if (msg.type === "ARM_CAPTURE" || msg.type === "FORCE_CAPTURE") {
      try {
        arm();
      } catch {}
    }
    if (msg.type === "STOP_CAPTURE") {
      try {
        disarm();
      } catch {}
    }
  });

  // Performance guard: charts are armed by the capture session.
  // Avoid scanning/hydrating chart DOM during the initial page load.


  window.__corneraiChartsUnifiedApi = {
    version: VERSION,
    build: buildUnified,
    emit,
    arm,
    disarm,
    get: () => window.__corneraiChartsUnified || null
  };

  try {
    console.log(PREFIX, "v" + VERSION, "unified charts module ready");
  } catch {}
})();
