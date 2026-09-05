(() => {
if(window.__cornerAIMenuV69191)return;window.__cornerAIMenuV69191=true;
  "use strict";
  const VERSION="12.6.12";
  const PREFIX = "[CornerAI MenuCapture]";
  let lastHash = "";
  let lastKey = "";
  let lastSent = 0;
  let captureEnabled = true; // FORCE_MENU_CAPTURE_ON 12.8.14

  const clean = v => String(v ?? "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const norm = v => clean(v).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const fixtureId = () => {
    try {
      const u = new URL(location.href);
      return u.searchParams.get("fixture") || ((u.pathname.match(/\/(?:fixture|partida|match|game)\/(\d+)/i) || [])[1] || null);
    } catch { return null; }
  };
  const hash = s => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); };
  const menuAliases = {
    pre_jogo: ["pre jogo", "pré jogo", "pre-jogo", "pré-jogo", "pre game", "upcoming"],
    pre_odds: ["pre odds", "pré odds", "pre-odds", "pré-odds"],
    ao_vivo: ["ao vivo", "live", "ao-vivo", "in play"],
    graficos: ["graficos", "gráficos", "charts", "graphs"],
    odds: ["odds", "cotas", "cotações", "cotacoes", "markets", "mercados"],
    dicas: ["dicas", "tips", "palpites", "predictions"],
    h2h: ["h2h", "confrontos", "head to head", "frente a frente"],
    estatisticas: ["estatisticas", "estatísticas", "stats", "statistics", "estatistica"],
    escalacoes: ["escalacoes", "escalações", "lineups", "line-up", "teams", "formacao", "formação"],
    rank: ["rank", "ranking", "classificacao", "classificação", "standings"],
    eventos: ["eventos", "events", "timeline", "linha do tempo", "cronologia"],
    escanteios: ["escanteios", "corners", "cantos", "corner"],
    xg: ["xg", "expected goals", "gols esperados", "x g"],
    posse: ["posse", "possession", "posse de bola"],
    finalizacoes: ["finalizacoes", "finalizações", "shots", "chutes", "total de chutes"],
    ataques: ["ataques", "attacks", "ataques perigosos", "dangerous attacks"],
    cartoes: ["cartoes", "cartões", "cards", "yellow", "red", "amarelos", "vermelhos"],
    substituicoes: ["substituicoes", "substituições", "substitutions", "subs"],
    jogadores: ["jogadores", "players", "player stats", "desempenho", "performance"],
    macd_xg: ["macd xg", "macd-xg", "macd"],
    grafico_xg: ["grafico xg", "gráfico xg", "xg chart"],
    analise_ia: ["analise de ia", "análise de ia", "ai analysis"],
    grafico_padrao: ["grafico padrao", "gráfico padrão", "standard chart"],
    barra_pressao: ["barra de pressao", "barra de pressão", "pressure bar"],
    ataques_perigosos: ["ataques perigosos", "dangerous attacks"],
    ataques: ["ataques", "attacks"]
  };
  function menuId(label, href = location.href) {
    const n = norm(label);
    for (const [id, aliases] of Object.entries(menuAliases)) if (aliases.some(a => n === norm(a) || n.includes(norm(a)))) return id;
    const p = norm(href);
    if (/pre.?jogo|pre.?game|upcoming/.test(p)) return "pre_jogo";
    if (/pre.?odds/.test(p)) return "pre_odds";
    if (/live|ao.?vivo|in.?play/.test(p)) return "ao_vivo";
    if (/graf|chart|graph/.test(p)) return "graficos";
    if (/odds|mercado|market/.test(p)) return "odds";
    if (/dica|tip|palpite|prediction/.test(p)) return "dicas";
    if (/h2h|head.?to.?head|confront/.test(p)) return "h2h";
    if (/estat|stat/.test(p)) return "estatisticas";
    if (/escal|line.?up/.test(p)) return "escalacoes";
    if (/rank|classific|standing/.test(p)) return "rank";
    return "unknown";
  }
  function root() {
    // Prefer painel de gráficos / detalhes da partida quando visível
    const chartRoot = document.querySelector(
      ".macd-wrapper, .pressure-grid, .chart-container, .standard-chart-container, " +
      ".slide-navigation, [class*='charts'], [class*='grafico'], .desktop-details-panel, " +
      "main,[role='main'],#content,.content,.main-content,[class*='content']"
    );
    return chartRoot || document.body || document.documentElement;
  }
  function text(el, cap = 1200) { return clean(el?.innerText || el?.textContent || "").slice(0, cap); }
  function chartPanelText() {
    const panels = document.querySelectorAll(
      ".macd-wrapper, .pressure-grid, .chart-container, .standard-chart-container, " +
      ".slide, [class*='chart'], [class*='grafico'], .pressure-block"
    );
    let out = "";
    for (const p of panels) {
      out += " " + text(p, 4000);
      if (out.length > 20000) break;
    }
    // Labels das abas de gráfico
    const tabs = [...document.querySelectorAll(".slide-navigation .slide-btn, button.slide-btn")]
      .map(b => text(b, 80)).filter(Boolean);
    if (tabs.length) out = "ABAS: " + tabs.join(" | ") + "\n" + out;
    return clean(out).slice(0, 25000);
  }
  function attrs(el) {
    const out = {};
    for (const a of [...(el?.attributes || [])]) if (/^(aria-|data-)/i.test(a.name)) out[a.name] = String(a.value).slice(0, 500);
    return out;
  }
  function discoverMenus() {
    const seen = new Set(), out = [];
    const selectors = "nav a, nav button, header a, [role='navigation'] a, [role='tab'], [role='menuitem'], [role='tablist'] [role='tab'], a[href], button[data-tab], [data-menu], [class*='tab'], [class*='menu-item'], [class*='nav-item']";
    for (const el of document.querySelectorAll(selectors)) {
      const label = text(el, 180); const href = el.href || el.getAttribute("href") || el.getAttribute("data-href") || el.getAttribute("data-url") || el.getAttribute("to") || "";
      if (!label && !href) continue;
      let u = href; try { u = new URL(href || location.href, location.href).href; } catch {}
      if (u && !/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(u) && u !== location.href) continue;
      const id = menuId(label, u); const key = `${id}|${label}|${u}`; if (seen.has(key)) continue; seen.add(key);
      out.push({ id, label, href: u, active: el.matches("[aria-current='page'],[aria-selected='true'],.active,.selected") || /active|selected|current/i.test(String(el.className || "")), source: "dom" });
      if (out.length >= 120) break;
    }
    return out;
  }
  function tables(r) {
    return [...r.querySelectorAll("table")].slice(0, 80).map((t, ti) => ({
      index: ti,
      caption: text(t.querySelector("caption"), 250),
      headers: [...t.querySelectorAll("thead th,thead td")].map(x => text(x, 250)).slice(0, 50),
      rows: [...t.querySelectorAll("tbody tr, tr")].slice(0, 400).map(tr => [...tr.querySelectorAll("th,td")].map(td => text(td, 500)).slice(0, 50)).filter(row => row.length)
    }));
  }
  function cards(r) {
    const nodes = [...r.querySelectorAll("[class*='card'],[class*='market'],[class*='odds'],[class*='fixture'],[class*='stat'],[class*='team'],[class*='rank'],[class*='tip']")];
    const seen = new Set(), out = [];
    for (const el of nodes) {
      const t = text(el, 900); if (!t || t.length < 2) continue;
      const key = hash(t); if (seen.has(key)) continue; seen.add(key);
      out.push({ text: t, tag: el.tagName.toLowerCase(), className: String(el.className || "").slice(0, 240), attrs: attrs(el) });
      if (out.length >= 500) break;
    }
    return out;
  }
  function charts(r) {
    const out = [];
    const scope = r || document;
    const nodes = [...scope.querySelectorAll(
      "svg,[role='img'],canvas,[data-chart],[class*='chart'],[class*='graph']," +
      ".macd-wrapper, .pressure-grid, .pressure-block, .slide-btn, .line-chart-canvas"
    )];
    for (const el of nodes.slice(0, 160)) {
      const labels = [...el.querySelectorAll("[aria-label],[title],[data-minute],[data-value],[data-home-value],[data-away-value]")]
        .slice(0, 500)
        .map(x => ({
          aria: x.getAttribute("aria-label"),
          title: x.getAttribute("title"),
          minute: x.getAttribute("data-minute"),
          value: x.getAttribute("data-value"),
          homeValue: x.getAttribute("data-home-value"),
          awayValue: x.getAttribute("data-away-value")
        }))
        .filter(x => Object.values(x).some(v => v != null && v !== ""));
      // Pontos de polyline SVG
      if (el.tagName === "svg" || el.querySelector?.("polyline,path")) {
        const poly = el.tagName === "polyline" ? el : el.querySelector("polyline");
        if (poly) {
          const pts = (poly.getAttribute("points") || "").trim().split(/[\s,]+/).filter(Boolean);
          if (pts.length >= 4) labels.push({ polylinePoints: pts.slice(0, 80).join(",") });
        }
      }
      const label = clean(el.getAttribute("aria-label") || el.getAttribute("title") || el.querySelector?.("title")?.textContent || el.className || "");
      const visible = text(el, 8000);
      if (!label && !visible && !labels.length) continue;
      out.push({
        tag: el.tagName.toLowerCase(),
        label: String(label).slice(0, 200),
        text: visible,
        className: String(el.className || "").slice(0, 120),
        points: labels
      });
    }
    // Blocos de pressão (texto estruturado)
    document.querySelectorAll(".pressure-block").forEach((block, i) => {
      const interval = text(block.querySelector(".pressure-interval"), 40);
      const pct = text(block.querySelector(".pressure-pct"), 20);
      if (interval || pct) out.push({ tag: "pressure-block", label: interval || ("block-" + i), text: pct, points: [{ interval, pct }] });
    });
    return out;
  }
  function odds(r) {
    const out = [], seen = new Set();
    const nodes = r.querySelectorAll("[data-odd],[data-odds],[data-price],[data-quota],[data-cotacao],[class*='odd'],[class*='quota'],[class*='price']");
    for (const el of nodes) {
      const raw = el.getAttribute("data-odd") || el.getAttribute("data-odds") || el.getAttribute("data-price") || el.getAttribute("data-quota") || el.getAttribute("data-cotacao") || text(el, 80);
      const m = String(raw).replace(",", ".").match(/(?:^|\s)(\d{1,3}(?:\.\d{1,4})?)(?:\s|$)/); if (!m) continue;
      const odd = Number(m[1]); if (!Number.isFinite(odd) || odd < 1.01 || odd > 1000) continue;
      const parent = el.closest("[data-market],[data-market-name],[data-bet],[class*='market']") || el.parentElement;
      const market = clean(el.getAttribute("data-market") || parent?.getAttribute?.("data-market") || parent?.getAttribute?.("data-market-name") || parent?.querySelector?.("[data-market-name],.market-name")?.textContent || "");
      const selection = clean(el.getAttribute("data-selection") || el.getAttribute("data-outcome") || el.getAttribute("aria-label") || el.getAttribute("title") || text(parent, 220));
      const key = `${market}|${selection}|${odd}`; if (seen.has(key)) continue; seen.add(key);
      out.push({ market, selection, odds: odd, line: el.getAttribute("data-line") || parent?.getAttribute?.("data-line") || null, bookmaker: el.getAttribute("data-bookmaker") || parent?.getAttribute?.("data-bookmaker") || null });
      if (out.length >= 1500) break;
    }
    return out;
  }
  function detectChartsContext() {
    const slideNav = document.querySelector(".slide-navigation, .slide-navigation-container");
    const chartDom = document.querySelector(
      ".macd-wrapper, .pressure-grid, .pressure-block, canvas#line-chart, " +
      ".chart-container, .standard-chart-container, .line-chart-canvas, [class*='macd']"
    );
    const topTabs = [...document.querySelectorAll("a,button,[role='tab']")];
    const graficosTab = topTabs.find(el => {
      const t = norm(text(el, 48));
      return /^(graficos|gráficos|charts|graphs)$/.test(t) || /\bgraficos?\b|\bcharts?\b/.test(t);
    });
    const graficosActive = !!(graficosTab && (
      graficosTab.matches("[aria-selected='true'],.active,.selected") ||
      /active|selected|current/i.test(String(graficosTab.className || "")) ||
      /will-change/i.test(String(graficosTab.getAttribute("style") || ""))
    ));
    let activeSlide = null;
    const slideBtns = [...document.querySelectorAll(".slide-navigation .slide-btn, button.slide-btn")];
    for (const b of slideBtns) {
      const label = text(b, 60);
      const st = String(b.getAttribute("style") || "");
      const cls = String(b.className || "");
      const active = /will-change/i.test(st) || /\bactive\b|\bselected\b/i.test(cls) || b.getAttribute("aria-selected") === "true";
      if (active && label) { activeSlide = label; break; }
    }
    if (!activeSlide && document.querySelector(".macd-wrapper, [class*='macd']")) activeSlide = "MACD XG";
    if (!activeSlide && document.querySelector(".pressure-grid, .pressure-block")) activeSlide = "BARRA DE PRESSÃO";
    const onCharts = !!(slideNav || chartDom || graficosActive || activeSlide);
    return { onCharts, graficosActive, activeSlide, slideCount: slideBtns.length, hasChartDom: !!chartDom };
  }
  function capture(force = false) {
    if (!captureEnabled) return;
    const now = Date.now();
    if (!force && now - lastSent < 1400) return;
    const r = root(), menus = discoverMenus();
    const ctx = detectChartsContext();
    // Se o painel de gráficos está visível, força menuId=graficos
    // (não deixa a aba AO VIVO do topo sobrescrever)
    let active;
    if (ctx.onCharts) {
      active = {
        id: "graficos",
        label: ctx.activeSlide ? ("GRÁFICOS · " + ctx.activeSlide) : "GRÁFICOS",
        href: location.href,
        active: true,
        chartSlide: ctx.activeSlide || null
      };
    } else {
      active = menus.find(x => x.active)
        || menus.find(x => x.id !== "unknown")
        || { id: menuId("", location.href), label: "", href: location.href, active: true };
    }
    let mainText = text(r, 120000);
    let chartPayload = [];
    if (active.id === "graficos" || ctx.onCharts) {
      const chartTxt = chartPanelText();
      if (chartTxt && chartTxt.length > 40) mainText = (chartTxt + "\n" + mainText).slice(0, 120000);
      chartPayload = charts(document);
    } else {
      chartPayload = charts(r);
    }
    const discoveredIds = [...new Set([
      ...menus.map(m => m.id),
      ...(ctx.onCharts ? ["graficos"] : []),
      active.id
    ].filter(Boolean))];
    const payload = {
      version: VERSION, fixtureId: fixtureId(), url: location.href, title: clean(document.title), timestamp: now,
      menuId: active.id, menuLabel: active.label, pageKey: `${location.pathname}${location.search}`,
      activeMenu: active, menus, discoveredIds, chartContext: ctx,
      coverage: {
        hasStats: /estat|stat|xg|escanteio|corner|ataque|shot|posse|possession/i.test(mainText || ""),
        hasEvents: /evento|event|timeline|minuto|gol|cart[aã]o/i.test(mainText || ""),
        hasXG: /\bxg\b|expected goals|gols esperados|macd/i.test(mainText || ""),
        hasOdds: /odds|cota|mercado|1x2/i.test(mainText || ""),
        hasCharts: ctx.onCharts || chartPayload.length > 0,
        chartSlide: ctx.activeSlide || null,
        menuCount: menus.length
      },
      headings: [...r.querySelectorAll("h1,h2,h3,h4")].map(x => text(x, 300)).filter(Boolean).slice(0, 300),
      text: mainText, textLength: (mainText||"").length, tables: tables(r), charts: chartPayload, cards: cards(r), links: menus,
      buttons: [...document.querySelectorAll(".slide-btn, button, [role='button']")].map(x => ({ text: text(x, 220), attrs: attrs(x) })).filter(x => x.text).slice(0, 500),
      aria: [...r.querySelectorAll("[aria-label],[title]")].map(x => ({ text: text(x, 180), aria: x.getAttribute("aria-label"), title: x.getAttribute("title") })).filter(x => x.aria || x.title).slice(0, 800),
      odds: odds(r), jsonLd: [...document.querySelectorAll("script[type='application/ld+json']")].map(x => String(x.textContent || "").slice(0, 20000)).slice(0, 20)
    };
    const serialized = JSON.stringify(payload); const h = hash(serialized); const key = `${payload.menuId}|${payload.pageKey}|${ctx.activeSlide || ""}`;
    if (!force && h === lastHash && key === lastKey) return;
    lastHash = h; lastKey = key; lastSent = now;
    try { chrome.runtime.sendMessage({ type: "MENU_SNAPSHOT", payload }); } catch (e) { console.debug(PREFIX, e); }
  }
  function hookNavigation() {
    for (const method of ["pushState", "replaceState"]) {
      const original = history[method]; history[method] = function (...args) { const r = original.apply(this, args); setTimeout(() => capture(true), 250); return r; };
    }
    window.addEventListener("popstate", () => setTimeout(() => capture(true), 250));
    document.addEventListener("click", e => { if (!isFixturePageMenu()) return; const el = e.target?.closest?.("a,button,[role='tab'],[role='menuitem']"); if (el) setTimeout(() => capture(true), 700); }, true);
  }
  const observer = new MutationObserver(() => { clearTimeout(window.__cornerAIMenuTimer); window.__cornerAIMenuTimer = setTimeout(() => capture(false), 1200); });
  function isFixturePageMenu() {
    try {
      const u = new URL(location.href);
      if (u.searchParams.get("fixture")) return true;
      return /\/(?:fixture|partida|match|game)\/\d+/i.test(u.pathname);
    } catch { return false; }
  }
  function start() {
    hookNavigation();
    // Pre-activation: zero menu scans. Activation is explicit.
    // The observer is attached lazily after ARM_CAPTURE.
  }
  function activateMenuCapture(){
    captureEnabled = true;
    if(!isFixturePageMenu()) return;
    const obsRoot = document.querySelector("nav,[role='navigation'],[role='tablist'],.slide-navigation,main,.desktop-details-panel") || document.body || document.documentElement;
    if (obsRoot && !obsRoot.__corneraiMenuObserved) {
      observer.observe(obsRoot, { childList: true, subtree: true, characterData: false, attributes: true, attributeFilter: ["aria-current", "aria-selected", "class"] });
      try{obsRoot.__corneraiMenuObserved=true}catch{}
    }
    setTimeout(() => capture(true), 120);
  }
  function deactivateMenuCapture(){
    captureEnabled=false;
    try{observer.disconnect()}catch{}
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true }); else start();
  // ---------- Controlled menu open + capture + restore ----------
  let sweepActive = false;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function findClickableForMenu(menu) {
    // Prefer exact match on visible tabs/buttons, then href.
    const selectors = "[role='tab'],[role='menuitem'],nav a,nav button,header a,[class*='tab'],[class*='menu-item'],[class*='nav-item'],button[data-tab],[data-menu],a[href]";
    const nodes = [...document.querySelectorAll(selectors)];
    const wantLabel = norm(menu.label || "");
    const wantHref = menu.href || "";
    let best = null;
    for (const el of nodes) {
      const label = norm(text(el, 180));
      const href = el.href || el.getAttribute("href") || el.getAttribute("data-href") || "";
      if (wantLabel && (label === wantLabel || label.includes(wantLabel) || wantLabel.includes(label))) {
        best = el; break;
      }
      if (wantHref && href && href === wantHref) { best = el; break; }
    }
    return best;
  }

  function snapshotActiveState() {
    const active = document.querySelector("[role='tab'][aria-selected='true'],[role='tab'][aria-current='page'],[aria-current='page'],.active[role='tab'],.selected[role='tab']");
    return {
      el: active || null,
      label: active ? text(active, 180) : "",
      href: location.href,
      scrollY: window.scrollY || 0
    };
  }

  function softClick(el) {
    if (!el) return false;
    try {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      return true;
    } catch {
      try { el.click(); return true; } catch { return false; }
    }
  }

  async function controlledMenuSweep(options = {}) {
    if (sweepActive) return { ok: false, error: "sweep_already_active", opened: 0, restored: false };
    sweepActive = true;
    try {
      window.__corneraiMenuSweep = window.__corneraiMenuSweep || {};
      window.__corneraiMenuSweep.active = true;
    } catch {}
    // Default: clicks controlados em menus prioritários (escanteios/estatisticas/h2h/odds/graficos)
    // quando em página de fixture. allowClicks=false força modo passivo total.
    const onFixture = isFixturePageMenu() || /^\d{5,}$/.test(String(options.fixtureId||""));
    const allowClicks = options.allowClicks !== false && onFixture;
    const maxOpen = allowClicks ? Math.min(Number(options.maxOpen) || 14, 18) : 0;
    const waitMs = Math.min(Number(options.waitMs) || 550, 900);
    const defaultPrefer = ["ao_vivo","estatisticas","escanteios","xg","graficos","macd_xg","grafico_xg","analise_ia","grafico_padrao","barra_pressao","ataques_perigosos","eventos","finalizacoes","ataques","cartoes","substituicoes","jogadores","posse","h2h","odds","pre_jogo","pre_odds","dicas","rank","escalacoes"];
    // Caller can pass preferIds as array to prioritize gaps (odds/h2h/estatisticas)
    const preferList = Array.isArray(options.preferIds) && options.preferIds.length
      ? [...options.preferIds, ...defaultPrefer.filter(id => !options.preferIds.includes(id))]
      : defaultPrefer;
    const preferIds = new Set(preferList);
    const preferRank = Object.fromEntries(preferList.map((id, i) => [id, i]));
    const opened = [];
    const errors = [];
    let restored = false;
    const original = snapshotActiveState();

    try {
      // Baseline capture of current view.
      capture(true);
      await sleep(200);

      const menus = discoverMenus();
      // Rank: preferred semantic ids first (caller gaps first), skip already active, limit count.
      const ranked = menus
        .filter(m => m.id !== "unknown" && !m.active)
        .sort((a, b) => {
          const ra = preferRank[a.id] ?? 99;
          const rb = preferRank[b.id] ?? 99;
          return ra - rb || String(a.label).localeCompare(String(b.label));
        })
        .slice(0, maxOpen);

      for (const menu of ranked) {
        const el = findClickableForMenu(menu);
        if (!el) { errors.push({ id: menu.id, reason: "element_not_found" }); continue; }
        // Avoid navigation away from the fixture page when href points elsewhere.
        const href = el.href || el.getAttribute("href") || "";
        const tag = (el.tagName || "").toLowerCase();
        if (tag === "a" && href) {
          try {
            const u = new URL(href, location.href);
            if (u.pathname !== location.pathname) {
              errors.push({ id: menu.id, reason: "would_navigate_away" });
              continue;
            }
          } catch {
            errors.push({ id: menu.id, reason: "bad_href" });
            continue;
          }
        }
        const ok = softClick(el);
        if (!ok) { errors.push({ id: menu.id, reason: "click_failed" }); continue; }
        await sleep(waitMs);
        capture(true);
        opened.push({ id: menu.id, label: menu.label });
      }

      // Restore original active tab/view (multiple strategies).
      if (original.el && document.contains(original.el)) {
        softClick(original.el);
        await sleep(waitMs);
        restored = true;
      }
      if (!restored && original.label) {
        const restoreTarget = findClickableForMenu({ id: "restore", label: original.label, href: original.href });
        if (restoreTarget) {
          softClick(restoreTarget);
          await sleep(waitMs);
          restored = true;
        }
      }
      if (!restored && original.href && original.href !== location.href) {
        // Same-path hash/query restore only — never navigate to another fixture.
        try {
          const u = new URL(original.href, location.href);
          if (u.pathname === location.pathname) {
            const byHref = [...document.querySelectorAll("a[href],[role='tab']")].find(el => {
              const h = el.href || el.getAttribute("href") || "";
              return h && (h === original.href || h.endsWith(u.hash || "") && u.hash);
            });
            if (byHref) { softClick(byHref); await sleep(waitMs); restored = true; }
          }
        } catch {}
      }
      try { window.scrollTo(0, original.scrollY || 0); } catch {}
      // Final capture of restored state.
      capture(true);

      const result = {
        ok: true,
        opened: opened.length,
        menus: opened,
        restored,
        errors: errors.slice(0, 20),
        discovered: menus.length,
        at: Date.now()
      };
      try {
        window.__corneraiMenuSweep = window.__corneraiMenuSweep || {};
        window.__corneraiMenuSweep.lastResult = result;
        window.__corneraiMenuSweep.active = false;
      } catch {}
      return result;
    } catch (e) {
      const fail = { ok: false, error: e?.message || String(e), opened: opened.length, restored, errors, at: Date.now() };
      try {
        window.__corneraiMenuSweep = window.__corneraiMenuSweep || {};
        window.__corneraiMenuSweep.lastResult = fail;
        window.__corneraiMenuSweep.active = false;
      } catch {}
      return fail;
    } finally {
      sweepActive = false;
    }
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    // ARM_CAPTURE/STOP_CAPTURE: content.js é o dono da resposta (evita
    // corrida entre múltiplos listeners fechando o canal — CS_REJECTION).
    if (msg?.type === "ARM_CAPTURE") { activateMenuCapture(); return false; }
    if (msg?.type === "STOP_CAPTURE") { deactivateMenuCapture(); return false; }

    if (msg?.type === "MENU_PRIME") {
      if(!captureEnabled){sendResponse({ok:false,error:"CAPTURA | sessão não armada"});return true;}
      try {
        const menus=discoverMenus();
        window.__corneraiMenuSweep = window.__corneraiMenuSweep || {};
        window.__corneraiMenuSweep.primedAt=Date.now();
        window.__corneraiMenuSweep.discovered=menus.length;
        window.__corneraiMenuSweep.discoveredIds=[...new Set(menus.map(m=>m.id).filter(Boolean))];
        capture(true);
        sendResponse({ok:true,discovered:menus.length,ids:window.__corneraiMenuSweep.discoveredIds});
      } catch(e){ sendResponse({ok:false,error:e?.message||String(e)}); }
      return true;
    }
    if (msg?.type === "MENU_SWEEP") {
      const opts={...(msg.options||{})};
      const localFid=(()=>{try{const u=new URL(location.href);const q=u.searchParams.get("fixture");return q||document.querySelector("[data-fixture-id]")?.getAttribute("data-fixture-id")||"";}catch{return ""}})();
      if(opts.fixtureId && localFid && String(opts.fixtureId)!==String(localFid)){sendResponse({ok:false,error:"fixture_mismatch"});return true;}
      controlledMenuSweep(opts)
        .then(r => sendResponse(r))
        .catch(e => sendResponse({ ok: false, error: e?.message || String(e) }));
      return true;
    }
    if (msg?.type === "MENU_CAPTURE_NOW") {
      if(!captureEnabled){sendResponse({ok:false,error:"CAPTURA | sessão não armada"});return true;}
      try { capture(true); sendResponse({ ok: true }); }
      catch (e) { sendResponse({ ok: false, error: e.message }); }
      return true;
    }
  });
  window.addEventListener("cornerai-menu-sweep", (ev) => {
    try { controlledMenuSweep(ev?.detail || {}); } catch (e) { console.debug(PREFIX, e); }
  });
  console.debug(PREFIX, "v" + VERSION, location.href);
})();
