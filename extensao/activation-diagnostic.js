(() => {
if(window.__cornerAIActivationV1287)return;window.__cornerAIActivationV1287=true;
  "use strict";
  /**
   * CornerAI — Módulo de Diagnóstico de Ativação (SokkerPro)
   * Captura: runtime errors, network failures, DOM readiness, message-passing health.
   * Acionado no ciclo de vida de ARM_CAPTURE / AUTO_CAPTURE_READY / RUN_ACTIVATION_DIAG.
   */
  const MOD_VERSION="12.8.9";
  const PREFIX = "[CornerAI:ActDiag]";
  const MAX_ERRORS = 40;
  const MAX_NETWORK = 60;
  const ACTIVATION_WINDOW_MS = 15000;

  const buf = {
    runtimeErrors: [],
    networkFailures: [],
    domChecks: null,
    messaging: null,
    activation: null,
    siteHealth: null,
    startedAt: 0,
    lastReport: null
  };

  let hooksInstalled = false;
  let originalFetch = null;
  let originalXHROpen = null;
  let originalXHRSend = null;

  function ts() {
    return new Date().toISOString();
  }

  function pushRing(arr, item, max) {
    arr.push(item);
    if (arr.length > max) arr.splice(0, arr.length - max);
  }

  function isSokkerUrl(u) {
    try {
      return /sokkerpro\.com/i.test(String(u || location.href));
    } catch {
      return false;
    }
  }

  // ─── 1) Runtime errors ─────────────────────────────────────────────
  function captureRuntimeError(payload) {
    pushRing(buf.runtimeErrors, {
      at: ts(),
      epoch: Date.now(),
      type: payload.type || "Error",
      message: String(payload.message || "").slice(0, 500),
      source: String(payload.source || "").slice(0, 300),
      lineno: payload.lineno ?? null,
      colno: payload.colno ?? null,
      stack: String(payload.stack || "").slice(0, 1200),
      duringActivation: !!(buf.activation && Date.now() - buf.startedAt < ACTIVATION_WINDOW_MS)
    }, MAX_ERRORS);
  }

  function installRuntimeHooks() {
    if (window.__corneraiActDiagRuntime) return;
    window.__corneraiActDiagRuntime = true;

    window.addEventListener("error", (ev) => {
      const msg = String(ev?.message || ev?.error?.message || "").trim();
      // Erro de layout benigno do próprio SokkerPro; não deve bloquear a ativação.
      if (/^ResizeObserver loop (completed with undelivered notifications|limit exceeded)\.?$/i.test(msg)) return;
      // Cross-origin / Script error sem detalhe — não poluir ativação.
      if (!msg || /^script error\.?$/i.test(msg)) return;
      const filename = (ev && (ev.filename || ev.filename === "")) ? (ev.filename || "inline") : (ev?.error?.stack ? "stack" : "unknown");
      captureRuntimeError({
        type: "window.onerror",
        message: msg || String(ev?.error || "unknown"),
        source: String(filename).slice(0, 300),
        lineno: ev?.lineno ?? null,
        colno: ev?.colno ?? null,
        stack: ev?.error?.stack || ""
      });
    }, true);

    window.addEventListener("unhandledrejection", (ev) => {
      const reason = ev.reason;
      captureRuntimeError({
        type: "unhandledrejection",
        message: reason?.message || String(reason),
        source: "promise",
        stack: reason?.stack
      });
    });

    // Console.error interception (não substitui console — só observa)
    try {
      const origErr = console.error.bind(console);
      console.error = function (...args) {
        try {
          const msg = args.map(a => {
            if (a instanceof Error) return a.message + (a.stack ? "\n" + a.stack : "");
            if (typeof a === "object") try { return JSON.stringify(a).slice(0, 300); } catch { return String(a); }
            return String(a);
          }).join(" ").slice(0, 500);
          if (/cornerai|content script|extension context|message port|receiving end/i.test(msg)) {
            captureRuntimeError({ type: "console.error", message: msg, source: "console" });
          }
        } catch {}
        return origErr(...args);
      };
    } catch {}
  }

  // ─── 2) Network monitoring ─────────────────────────────────────────
  function isOptionalLocalUrl(u) {
    try {
      const s = String(u || "");
      return /^(https?:\/\/)(127\.0\.0\.1|localhost):(8765|8000)\/|^(wss?:\/\/)(127\.0\.0\.1|localhost):8090\//i.test(s);
    } catch { return false; }
  }
  function recordNetworkFailure(entry) {
    const optional = entry?.optional === true || isOptionalLocalUrl(entry?.url);
    pushRing(buf.networkFailures, {
      at: ts(),
      epoch: Date.now(),
      optional,
      ...entry,
      duringActivation: !!(buf.activation && Date.now() - buf.startedAt < ACTIVATION_WINDOW_MS)
    }, MAX_NETWORK);
  }
  function requiredNetworkFailures(list) {
    return (list || []).filter(n => n && !n.optional);
  }

  function installNetworkHooks() {
    if (window.__corneraiActDiagNet) return;
    window.__corneraiActDiagNet = true;

    // fetch
    try {
      originalFetch = window.fetch.bind(window);
      window.fetch = async function (input, init) {
        const url = typeof input === "string" ? input : (input?.url || String(input));
        const method = (init?.method || input?.method || "GET").toUpperCase();
        const t0 = Date.now();
        try {
          const res = await originalFetch(input, init);
          const ms = Date.now() - t0;
          if (!res.ok && (res.status >= 400 || res.status === 0)) {
            recordNetworkFailure({
              kind: "fetch",
              url: String(url).slice(0, 400),
              method,
              status: res.status,
              statusText: res.statusText || "",
              durationMs: ms,
              sokker: isSokkerUrl(url),
              optional: isOptionalLocalUrl(url)
            });
          } else if (ms > 12000 && isSokkerUrl(url)) {
            recordNetworkFailure({
              kind: "fetch-slow",
              url: String(url).slice(0, 400),
              method,
              status: res.status,
              durationMs: ms,
              sokker: true,
              optional: isOptionalLocalUrl(url),
              note: "timeout-soft (>12s)"
            });
          }
          return res;
        } catch (err) {
          recordNetworkFailure({
            kind: "fetch-error",
            url: String(url).slice(0, 400),
            method,
            status: 0,
            durationMs: Date.now() - t0,
            message: err?.message || String(err),
            sokker: isSokkerUrl(url),
            optional: isOptionalLocalUrl(url)
          });
          throw err;
        }
      };
    } catch {}

    // XMLHttpRequest
    try {
      originalXHROpen = XMLHttpRequest.prototype.open;
      originalXHRSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (method, url, ...rest) {
        this.__corneraiDiag = { method: String(method || "GET").toUpperCase(), url: String(url || ""), t0: 0 };
        return originalXHROpen.call(this, method, url, ...rest);
      };
      XMLHttpRequest.prototype.send = function (...args) {
        const meta = this.__corneraiDiag || {};
        meta.t0 = Date.now();
        this.addEventListener("loadend", () => {
          const status = this.status;
          const ms = Date.now() - (meta.t0 || Date.now());
          if (status >= 400 || status === 0) {
            recordNetworkFailure({
              kind: "xhr",
              url: String(meta.url || "").slice(0, 400),
              method: meta.method || "GET",
              status,
              durationMs: ms,
              sokker: isSokkerUrl(meta.url),
              optional: isOptionalLocalUrl(meta.url)
            });
          }
        });
        this.addEventListener("error", () => {
          recordNetworkFailure({
            kind: "xhr-error",
            url: String(meta.url || "").slice(0, 400),
            method: meta.method || "GET",
            status: 0,
            durationMs: Date.now() - (meta.t0 || Date.now()),
            message: "network error",
            sokker: isSokkerUrl(meta.url),
            optional: isOptionalLocalUrl(meta.url)
          });
        });
        this.addEventListener("timeout", () => {
          recordNetworkFailure({
            kind: "xhr-timeout",
            url: String(meta.url || "").slice(0, 400),
            method: meta.method || "GET",
            status: 0,
            durationMs: Date.now() - (meta.t0 || Date.now()),
            message: "timeout",
            sokker: isSokkerUrl(meta.url),
            optional: isOptionalLocalUrl(meta.url)
          });
        });
        return originalXHRSend.apply(this, args);
      };
    } catch {}
  }

  // ─── 3) DOM readiness checks ───────────────────────────────────────
  function checkDom() {
    const q = (sel) => {
      try { return document.querySelector(sel); } catch { return null; }
    };
    const qa = (sel) => {
      try { return document.querySelectorAll(sel).length; } catch { return 0; }
    };

    const checks = [
      {
        id: "scoreboard",
        required: true,
        ok: !!(q(".scoreboard,[class*='scoreboard'],[class*='match-header'],.gs-match-info,[class*='live-score'],.fx-score,.match-score")),
        detail: "Cabeçalho / placar da partida"
      },
      {
        id: "live-clock",
        required: false,
        ok: !!(q(".gs-live-min,.gs-match-min,.match-clock,.live-clock,[data-live-minute],[class*='live-min']")),
        detail: "Relógio ao vivo"
      },
      {
        id: "stat-rows",
        required: false,
        ok: qa(".stat-values-row,.statistics-row,.stats-row,[class*='stat-values-row'],tr.stat-row,[data-stat]") > 0,
        detail: `Linhas de estatística (${qa(".stat-values-row,.statistics-row,.stats-row,[class*='stat-values-row'],tr.stat-row,[data-stat]")})`
      },
      {
        id: "teams-text",
        required: true,
        ok: (() => {
          try {
            if (typeof extractTeams === "function") {
              const t = extractTeams();
              return !!(t?.home && t?.away);
            }
          } catch {}
          const body = (document.body?.innerText || "").slice(0, 2000);
          return /\d\s*[xX×]\s*\d/.test(document.title || "") || body.length > 200;
        })(),
        detail: "Times / identidade da partida"
      },
      {
        id: "fixture-id",
        required: true,
        ok: (() => {
          try {
            if (typeof fixtureId === "function" && fixtureId()) return true;
          } catch {}
          try {
            if (window.__corneraiNetFixture && /^\d{5,}$/.test(String(window.__corneraiNetFixture))) return true;
          } catch {}
          try {
            const u = new URL(location.href);
            if (u.searchParams.get("fixture") || u.searchParams.get("matchId")) return true;
            if (/\/(?:fixture|partida|match|game)\/\d{5,}/i.test(u.pathname)) return true;
          } catch {}
          try {
            if (document.querySelector("[data-fixture-id],[data-match-id],[data-game-id],[data-event-id]")) return true;
          } catch {}
          return /fixture|partida|match/i.test(location.href);
        })(),
        detail: "Fixture ID na URL/DOM"
      },
      {
        id: "timeline-or-events",
        required: false,
        ok: qa("[class*='timeline'],[class*='incident'],[class*='event-list'],.events") > 0 ||
            /\d{1,3}['′]/.test((document.body?.innerText || "").slice(0, 4000)),
        detail: "Timeline / eventos"
      },
      {
        id: "charts-area",
        required: false,
        ok: qa("canvas,[class*='chart'],[class*='graf'],[class*='graph']") > 0,
        detail: "Área de gráficos"
      },
      {
        id: "document-ready",
        required: true,
        ok: document.readyState === "complete" || document.readyState === "interactive",
        detail: `readyState=${document.readyState}`
      },
      {
        id: "body-content",
        required: true,
        ok: (document.body?.innerText || "").length > 100,
        detail: `body length=${(document.body?.innerText || "").length}`
      }
    ];

    const requiredFailed = checks.filter(c => c.required && !c.ok).map(c => c.id);
    const optionalFailed = checks.filter(c => !c.required && !c.ok).map(c => c.id);

    buf.domChecks = {
      at: ts(),
      ok: requiredFailed.length === 0,
      requiredFailed,
      optionalFailed,
      checks,
      url: location.href,
      title: document.title || ""
    };
    return buf.domChecks;
  }

  // ─── 3.5) Site/Chart health ───────────────────────────────────────
  function inspectSiteHealth() {
    const roots=[...document.querySelectorAll(".macd-wrapper,.pressure-grid,#line-chart,.chart-container,.standard-chart-container,[class*=chart],[class*=macd],[class*=pressure]")].slice(0,20);
    const charts=roots.map((el,i)=>({i,tag:el.tagName,id:el.id||null,cls:String(el.className||"").slice(0,160),visible:!!(el.offsetParent!==null||el.getClientRects?.().length),width:Math.round(el.getBoundingClientRect?.().width||0),height:Math.round(el.getBoundingClientRect?.().height||0),canvas:!!el.querySelector?.("canvas")||el.tagName==="CANVAS",text:String(el.innerText||"").replace(/\s+/g," ").slice(0,180)}));
    const loading=[...document.querySelectorAll("body *")].filter(el=>/loading data|carregando|sem dados disponíveis|sem dados de xg/i.test(String(el.textContent||""))).length;
    const pageDiag=window.__corneraiPageDiag||{};
    const visible=charts.filter(c=>c.visible);
    const zeroSize=visible.filter(c=>c.width<20||c.height<20).length;
    const dataHints=visible.filter(c=>/\d|xg|attack|press|macd|corner|chute/i.test(c.text)).length;
    return {charts,totalCharts:charts.length,visibleCharts:visible.length,zeroSizeCharts:zeroSize,zeroSizeScope:"visible-only",chartDataHints:dataHints,loadingNodes:Math.min(loading,50),pageErrors:(pageDiag.errors||[]).length,pageRejections:(pageDiag.rejections||[]).length,longTasks:(pageDiag.longTasks||[]).length,resourceErrors:(pageDiag.resourceErrors||[]).length,wsErrors:(pageDiag.ws||[]).filter(x=>x.event==="error"||x.event==="close").length,chartMutations:Number(pageDiag.chartMutations||0),timestamp:Date.now()};
  }

  // ─── 4) Message-passing health ─────────────────────────────────────
  function testMessaging() {
    return new Promise((resolve) => {
      const started = Date.now();
      const result = {
        at: ts(),
        contentToBackground: null,
        backgroundLatencyMs: null,
        extensionContextValid: true,
        errors: []
      };

      try {
        if (!chrome?.runtime?.id) {
          result.extensionContextValid = false;
          result.errors.push("chrome.runtime.id ausente (contexto invalidado — recarregue a página)");
          buf.messaging = result;
          resolve(result);
          return;
        }
      } catch (e) {
        result.extensionContextValid = false;
        result.errors.push(e?.message || String(e));
        buf.messaging = result;
        resolve(result);
        return;
      }

      try {
        chrome.runtime.sendMessage({ type: "PING_BACKGROUND", diagnostic: true, ts: started }, (r) => {
          const err = chrome.runtime.lastError;
          result.backgroundLatencyMs = Date.now() - started;
          if (err) {
            result.contentToBackground = { ok: false, error: err.message };
            result.errors.push("BG: " + err.message);
          } else {
            result.contentToBackground = { ok: true, response: r || null };
          }
          try {
            chrome.storage.session.get(["__sw_alive_at"], (sr) => {
              const alive = sr && sr.__sw_alive_at ? Number(sr.__sw_alive_at) : null;
              result.swAliveAgeMs = alive != null ? Math.max(0, Date.now() - alive) : null;
              buf.messaging = result;
              resolve(result);
            });
          } catch {
            buf.messaging = result;
            resolve(result);
          }
        });
      } catch (e) {
        result.contentToBackground = { ok: false, error: e?.message || String(e) };
        result.errors.push(e?.message || String(e));
        buf.messaging = result;
        resolve(result);
      }

      // Safety timeout
      setTimeout(() => {
        if (!buf.messaging || buf.messaging.at === result.at && result.contentToBackground === null) {
          result.contentToBackground = { ok: false, error: "timeout 3s — service worker inativo?" };
          result.errors.push("timeout messaging");
          result.backgroundLatencyMs = Date.now() - started;
          buf.messaging = result;
          resolve(result);
        }
      }, 3000);
    });
  }

  // ─── Report builder ────────────────────────────────────────────────
  function severityOf(report) {
    if (!report.messaging?.extensionContextValid) return "critical";
    if (report.messaging?.contentToBackground?.ok === false) return "critical";
    if (report.dom?.requiredFailed?.length) return "high";
    if ((report.runtimeErrors || []).some(e => e.duringActivation)) return "high";
    if ((report.networkFailures || []).filter(n => n.duringActivation && n.sokker && !n.optional).length >= 3) return "medium";
    if (report.dom && !report.dom.ok) return "medium";
    return "ok";
  }

  function humanSummary(report) {
    const sev = report.severity || severityOf(report);
    if (sev === "ok") return "Ativação saudável — content ↔ background OK, DOM pronto, sem erros críticos.";
    const parts = [];
    if (!report.messaging?.extensionContextValid) parts.push("Contexto da extensão invalidado (recarregue a aba SokkerPRO).");
    if (report.messaging?.contentToBackground?.ok === false) parts.push("Falha de comunicação com o Service Worker: " + (report.messaging.contentToBackground.error || ""));
    if (report.dom?.requiredFailed?.length) parts.push("DOM incompleto: " + report.dom.requiredFailed.join(", "));
    const actErrs = (report.runtimeErrors || []).filter(e => e.duringActivation);
    if (actErrs.length) parts.push(`${actErrs.length} erro(s) JS durante ativação.`);
    const net = requiredNetworkFailures((report.networkFailures || []).filter(n => n.duringActivation));
    if (net.length) parts.push(`${net.length} falha(s) de rede na janela de ativação.`);
    return parts.join(" ") || "Problemas detectados — veja o JSON completo.";
  }

  async function buildReport(trigger) {
    const dom = checkDom();
    const messaging = await testMessaging();

    // Slice errors/network to activation window if we have one
    const since = buf.startedAt || 0;
    const runtimeErrors = buf.runtimeErrors.filter(e => !since || e.epoch >= since - 2000);
    const networkFailures = buf.networkFailures.filter(n => !since || n.epoch >= since - 2000);

    const report = {
      schema: "cornerai-activation-diag-1",
      version: MOD_VERSION,
      trigger: String(trigger || "manual"),
      at: ts(),
      epoch: Date.now(),
      activationStartedAt: buf.startedAt ? new Date(buf.startedAt).toISOString() : null,
      url: location.href,
      title: document.title || "",
      readyState: document.readyState,
      fixtureId: (() => { try { return typeof fixtureId === "function" ? fixtureId() : null; } catch { return null; } })(),
      dom,
      messaging,
      runtimeErrors,
      networkFailures,
      siteHealth: inspectSiteHealth(),
      counts: {
        runtimeErrors: runtimeErrors.length,
        networkFailures: requiredNetworkFailures(networkFailures).length,
        optionalNetworkFailures: networkFailures.filter(n => n && n.optional).length,
        domRequiredFailed: dom?.requiredFailed?.length || 0,
        domOptionalFailed: dom?.optionalFailed?.length || 0
      }
    };
    report.severity = severityOf(report);
    report.summary = humanSummary(report);
    report.ok = report.severity === "ok" || report.severity === "medium";
    buf.lastReport = report;
    return report;
  }

  // ─── Public API ────────────────────────────────────────────────────
  async function startActivationCycle(trigger) {
    buf.startedAt = Date.now();
    buf.activation = { trigger: String(trigger || "arm"), at: ts() };
    installRuntimeHooks();
    installNetworkHooks();
    // Snapshot DOM imediato + messaging; reavalia após estabilizar SPA.
    // SokkerPro SPA frequentemente monta scoreboard/teams após o 1º paint —
    // retry curto evita false-negative em domRequiredFailed.
    const early = await buildReport(trigger + ":start");
    let final = early;
    const delays = [600, 900, 1200];
    for (let i = 0; i < delays.length; i++) {
      await new Promise(r => setTimeout(r, delays[i]));
      final = await buildReport(trigger + ":settle");
      const reqFailed = (final.dom && Array.isArray(final.dom.requiredFailed))
        ? final.dom.requiredFailed
        : (buf.domChecks && Array.isArray(buf.domChecks.requiredFailed) ? buf.domChecks.requiredFailed : []);
      if (!reqFailed.length) break;
    }
    try {
      chrome.runtime.sendMessage({
        type: "ACTIVATION_DIAG_REPORT",
        payload: final
      }, () => { void chrome.runtime.lastError; });
    } catch {}
    try { console.log(PREFIX, final.severity, final.summary, final); } catch {}
    return final;
  }

  function installHooksEarly() {
    if (hooksInstalled) return;
    hooksInstalled = true;
    installRuntimeHooks();
    installNetworkHooks();
  }

  // Auto-install hooks on fixture pages so errors during SPA nav are caught
  installHooksEarly();

  // Message API
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || !msg.type) return;
    if (msg.type === "RUN_ACTIVATION_DIAG") {
      startActivationCycle(msg.trigger || "manual").then(report => {
        sendResponse({ ok: true, report });
      }).catch(e => {
        sendResponse({ ok: false, error: e?.message || String(e) });
      });
      return true;
    }
    if (msg.type === "GET_ACTIVATION_DIAG") {
      sendResponse({ ok: true, report: buf.lastReport, buffer: {
        runtimeErrors: buf.runtimeErrors.slice(-20),
        networkFailures: buf.networkFailures.slice(-20),
        startedAt: buf.startedAt
      }});
      return true;
    }
    if (msg.type === "ARM_CAPTURE" || msg.type === "FORCE_CAPTURE") {
      // Fire-and-forget activation diagnostic alongside arm
      try { startActivationCycle(msg.type); } catch {}
    }
  });

  // Expose for content.js integration
  window.__corneraiActivationDiag = {
    version: MOD_VERSION,
    start: startActivationCycle,
    report: () => buf.lastReport,
    checkDom,
    testMessaging,
    getBuffer: () => ({
      runtimeErrors: buf.runtimeErrors.slice(),
      networkFailures: buf.networkFailures.slice(),
      domChecks: buf.domChecks,
      messaging: buf.messaging
    })
  };

  try { console.log(PREFIX, "v" + MOD_VERSION, "hooks instalados", location.href); } catch {}
})();
