/**
 * CornerAI - Gemini Skill Connector & Integration Layer (v9.2.13+)
 * HTTP webhook + WebSocket streaming em tempo real.
 * Schema: cornerai-gemini-v1.1 (CPI_v2 + prediction_corner_2m + telemetria)
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAIGeminiConnector = Object.assign(root.CornerAIGeminiConnector || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function safeNum(v, fallback) {
    var n = Number(v);
    return Number.isFinite(n) ? n : (fallback !== undefined ? fallback : 0);
  }

  function formatPayloadForGemini(rawState) {
    if (!rawState || typeof rawState !== "object") return null;

    var minute = Number(rawState.minute);
    var extraMinute = Number(rawState.extraMinute) || 0;
    var clockDisplay = (Number.isFinite(minute) ? minute : "?") + (extraMinute ? "+" + extraMinute : "") + "'";

    var recentCorners = (Array.isArray(rawState.cornerEvents) ? rawState.cornerEvents : [])
      .slice(-12)
      .map(function (e) {
        return {
          minute: e.minute,
          extra: e.extraMinute || 0,
          side: e.side,
          period: e.period === 1 ? "1T" : (e.period === 2 ? "2T" : String(e.period || ""))
        };
      });

    var indicators = (rawState.chartData && rawState.chartData.cornerIndicatorTimeline) ||
                     rawState.cornerIndicatorTimeline ||
                     (rawState.aiFeed && rawState.aiFeed.indicators) ||
                     [];
    var latestIndicator = indicators.length ? indicators[indicators.length - 1] : null;

    var stats = rawState.stats || {};
    var intel = rawState.intelligence || {};
    var quality = rawState.quality || {};
    var analyst = rawState.analyst || {};
    var predPayload = rawState.predictivePayload || null;

    var cpiHome = null, cpiAway = null, cpiFormula = null;
    var am = (predPayload && predPayload.advanced_metrics) ||
             (analyst && analyst.advanced_metrics) || null;
    if (am && am.CPI_v2) {
      cpiHome = am.CPI_v2.home || null;
      cpiAway = am.CPI_v2.away || null;
      cpiFormula = am.CPI_v2.formula || null;
    }

    var pred2m = null;
    if (am && am.temporal && am.temporal.prediction_corner_2m) {
      pred2m = am.temporal.prediction_corner_2m;
    } else if (predPayload && predPayload.prediction_corner_2m) {
      pred2m = predPayload.prediction_corner_2m;
    }

    var appm = (latestIndicator && latestIndicator.appm) ||
               (am && am.APPM) ||
               { "1m": { home: 0, away: 0 }, "5m": { home: 0, away: 0 } };

    var pressureBarsSummary = null;
    if (analyst && analyst.pressure && analyst.pressure.bars && typeof analyst.pressure.bars === "object") {
      var barKeys = Object.keys(analyst.pressure.bars).slice(-3);
      if (barKeys.length) {
        pressureBarsSummary = {};
        barKeys.forEach(function (k) {
          pressureBarsSummary[k] = analyst.pressure.bars[k];
        });
      }
    }

    var oddsCorners = null;
    if (analyst && analyst.odds && Array.isArray(analyst.odds.corners) && analyst.odds.corners.length) {
      oddsCorners = analyst.odds.corners.slice(0, 6);
    }

    return {
      schemaVersion: "cornerai-gemini-v1.1",
      timestamp: Date.now(),
      matchContext: {
        fixtureId: rawState.fixtureId || null,
        homeTeam: rawState.home || "Mandante",
        awayTeam: rawState.away || "Visitante",
        score: {
          home: safeNum(rawState.score && rawState.score.home),
          away: safeNum(rawState.score && rawState.score.away)
        },
        clock: {
          minute: Number.isFinite(minute) ? minute : null,
          extraMinute: extraMinute,
          display: clockDisplay,
          status: rawState.liveStatus || "unknown"
        }
      },
      telemetryStats: {
        corners: {
          home: safeNum(stats.corners && stats.corners.home),
          away: safeNum(stats.corners && stats.corners.away)
        },
        dangerousAttacks: {
          home: safeNum(stats.dangerous && stats.dangerous.home),
          away: safeNum(stats.dangerous && stats.dangerous.away)
        },
        shotsOnTarget: {
          home: safeNum(stats.shotsOn && stats.shotsOn.home),
          away: safeNum(stats.shotsOn && stats.shotsOn.away)
        },
        xg: {
          home: safeNum(stats.xg && stats.xg.home),
          away: safeNum(stats.xg && stats.xg.away)
        },
        possession: {
          home: safeNum(stats.possession && stats.possession.home, null),
          away: safeNum(stats.possession && stats.possession.away, null)
        },
        appm: appm
      },
      momentum: {
        home: safeNum(intel.momentum && intel.momentum.home),
        away: safeNum(intel.momentum && intel.momentum.away),
        readinessScore: safeNum(intel.readiness),
        dataQualityScore: safeNum(quality.score)
      },
      intelligence: {
        CPI_v2: {
          home: cpiHome,
          away: cpiAway,
          formula: cpiFormula
        },
        prediction_corner_2m: pred2m ? {
          probability: pred2m.probability != null ? Number(pred2m.probability) : null,
          side: pred2m.side || pred2m.favoredSide || null,
          window: pred2m.window || "2m",
          calibrated: !!pred2m.calibrated,
          factors: pred2m.factors || pred2m.breakdown || null
        } : null,
        pressureBarsRecent: pressureBarsSummary
      },
      market: {
        cornersOdds: oddsCorners,
        oneXTwo: (analyst && analyst.odds && analyst.odds["1x2"]) || null
      },
      events: {
        recentCorners: recentCorners
      }
    };
  }

  /* ───────────────────────── HTTP ───────────────────────── */

  async function sendToGeminiSkill(endpointUrl, payload, apiKey) {
    if (!endpointUrl) throw new Error("URL do endpoint do Gemini não fornecida.");

    var headers = {
      "Content-Type": "application/json",
      "X-CornerAI-Schema": (payload && payload.schemaVersion) || "cornerai-gemini-v1.1",
      "X-CornerAI-Version": "9.2.13"
    };
    if (apiKey) headers["Authorization"] = "Bearer " + apiKey;

    try {
      var response = await fetch(endpointUrl, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error("HTTP Error " + response.status + ": " + response.statusText);
      }
      var result = null;
      var ct = response.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) {
        result = await response.json();
      } else {
        result = { text: await response.text() };
      }
      return { ok: true, result: result };
    } catch (error) {
      console.error("[CornerAI][GeminiConnector] HTTP error:", error);
      return { ok: false, error: error.message || String(error) };
    }
  }

  /* ───────────────────────── WebSocket Stream ───────────────────────── */

  var _ws = null;
  var _wsUrl = null;
  var _wsApiKey = null;
  var _wsWanted = false;
  var _wsReconnectTimer = null;
  var _wsHeartbeatTimer = null;
  var _wsRetry = 0;
  var _wsMaxRetry = 3;
  var _wsAutoReconnect = false; // desligado: Experience usa HTTP POST
  var _wsLastSentAt = 0;
  var _wsLastRecvAt = 0;
  var _wsSent = 0;
  var _wsRecv = 0;
  var _wsLastError = null;
  var _wsLastAnalysis = null;
  var _wsMinIntervalMs = 2500; // rate-limit push
  var _wsListeners = [];

  function _emit(evt, data) {
    for (var i = 0; i < _wsListeners.length; i++) {
      try { _wsListeners[i](evt, data); } catch (e) {}
    }
  }

  function onWsEvent(fn) {
    if (typeof fn === "function") _wsListeners.push(fn);
    return function off() {
      _wsListeners = _wsListeners.filter(function (f) { return f !== fn; });
    };
  }

  function wsStatus() {
    var state = "closed";
    if (_ws) {
      if (_ws.readyState === 0) state = "connecting";
      else if (_ws.readyState === 1) state = "open";
      else if (_ws.readyState === 2) state = "closing";
      else state = "closed";
    }
    return {
      wanted: _wsWanted,
      state: state,
      url: _wsUrl,
      hasKey: !!_wsApiKey,
      sent: _wsSent,
      recv: _wsRecv,
      retry: _wsRetry,
      lastSentAt: _wsLastSentAt,
      lastRecvAt: _wsLastRecvAt,
      lastError: _wsLastError,
      lastAnalysis: _wsLastAnalysis
    };
  }

  function _clearTimers() {
    if (_wsReconnectTimer) { clearTimeout(_wsReconnectTimer); _wsReconnectTimer = null; }
    if (_wsHeartbeatTimer) { clearInterval(_wsHeartbeatTimer); _wsHeartbeatTimer = null; }
  }

  function _scheduleReconnect() {
    if (!_wsWanted) return;
    if (_wsRetry >= _wsMaxRetry) {
      _wsWanted = false;
      _wsLastError = "max_retries";
      _clearTimers();
      _emit("error", { error: "max_retries", hint: "Servidor HTTP-only? Use Experience DB :3000 (POST) em vez de CONECTAR WS." });
      return;
    }
    var delay = Math.min(30000, 800 * Math.pow(1.6, _wsRetry));
    _wsRetry += 1;
    _wsReconnectTimer = setTimeout(function () {
      connectWebSocket(_wsUrl, _wsApiKey, { silent: true });
    }, delay);
  }

  /** URLs do Experience DB / Express HTTP — não devem virar WebSocket */
  function isHttpOnlyExperienceUrl(url) {
    var s = String(url || "");
    if (/:(3000)\b/.test(s) && !/\/gemini\/ws/i.test(s)) return true;
    if (/\/api\/v10\//i.test(s)) return true;
    if (/\/experience\/?$/i.test(s)) return true;
    return false;
  }

  function _startHeartbeat() {
    if (_wsHeartbeatTimer) clearInterval(_wsHeartbeatTimer);
    _wsHeartbeatTimer = setInterval(function () {
      if (!_ws || _ws.readyState !== 1) return;
      try {
        _ws.send(JSON.stringify({ type: "ping", ts: Date.now() }));
      } catch (e) {}
    }, 20000);
  }

  /**
   * Conecta ao endpoint WebSocket da Skill.
   * Aceita ws:// ou wss:// — se receber http(s) converte automaticamente.
   */
  function connectWebSocket(url, apiKey, opts) {
    opts = opts || {};
    if (!url) return { ok: false, error: "URL WebSocket obrigatória" };

    var raw = String(url).trim();
    // Experience DB (:3000) é HTTP-only — não tentar WS nem retry
    if (isHttpOnlyExperienceUrl(raw)) {
      _wsWanted = false;
      _clearTimers();
      _wsLastError = "http_only_experience";
      return {
        ok: false,
        error: "http_only_experience",
        hint: "Use o botão Experience DB :3000 (POST HTTP). WebSocket não está disponível em :3000.",
        status: wsStatus()
      };
    }

    var u = raw;
    if (u.indexOf("http://") === 0) u = "ws://" + u.slice(7);
    if (u.indexOf("https://") === 0) u = "wss://" + u.slice(8);
    // se for path HTTP telemetry do receiver :8090, troca para /ws
    if (/\/gemini\/telemetry\/?$/.test(u)) {
      u = u.replace(/\/gemini\/telemetry\/?$/, "/gemini/ws");
    }
    if (u.indexOf("ws://") !== 0 && u.indexOf("wss://") !== 0) {
      return { ok: false, error: "URL deve começar com ws:// ou wss://" };
    }

    _wsWanted = true;
    _wsAutoReconnect = !!(opts && opts.autoReconnect);
    _wsUrl = u;
    _wsApiKey = apiKey || null;
    _clearTimers();
    _wsRetry = 0;

    // fecha anterior
    try {
      if (_ws) {
        _ws.onclose = null;
        _ws.onerror = null;
        _ws.onmessage = null;
        if (_ws.readyState === 0 || _ws.readyState === 1) _ws.close();
      }
    } catch (e) {}

    try {
      var qs = "";
      if (_wsApiKey) {
        qs = (u.indexOf("?") >= 0 ? "&" : "?") + "token=" + encodeURIComponent(_wsApiKey);
      }
      _ws = new WebSocket(u + qs);
    } catch (e) {
      _wsLastError = e.message || String(e);
      _scheduleReconnect();
      return { ok: false, error: _wsLastError };
    }

    _ws.onopen = function () {
      _wsRetry = 0;
      _wsLastError = null;
      _startHeartbeat();
      _emit("open", wsStatus());
      // hello
      try {
        _ws.send(JSON.stringify({
          type: "hello",
          schema: "cornerai-gemini-ws-1",
          version: "9.2.13",
          ts: Date.now()
        }));
      } catch (e) {}
    };

    _ws.onmessage = function (ev) {
      _wsLastRecvAt = Date.now();
      _wsRecv += 1;
      var data = null;
      try { data = JSON.parse(ev.data); } catch (e) { data = { raw: ev.data }; }
      if (data && data.type === "pong") return;
      if (data && (data.analysis || data.type === "analysis" || data.action)) {
        _wsLastAnalysis = data.analysis || data;
      }
      _emit("message", data);
    };

    _ws.onerror = function () {
      _wsLastError = "ws_error";
      _emit("error", { error: "ws_error" });
    };

    _ws.onclose = function () {
      _clearTimers();
      _emit("close", wsStatus());
      // Sem loop infinito: reconnect só se autoReconnect explícito
      if (_wsWanted && _wsAutoReconnect) _scheduleReconnect();
      else _wsWanted = false;
    };

    if (!opts.silent) _emit("connecting", { url: u });
    return { ok: true, url: u, status: wsStatus() };
  }

  function disconnectWebSocket() {
    _wsWanted = false;
    _clearTimers();
    try {
      if (_ws) {
        _ws.onclose = null;
        _ws.close();
      }
    } catch (e) {}
    _ws = null;
    _emit("close", wsStatus());
    return { ok: true, status: wsStatus() };
  }

  /**
   * Envia payload pelo WebSocket (rate-limited).
   * @returns {{ok:boolean, skipped?:boolean, error?:string}}
   */
  function sendViaWebSocket(payload, force) {
    if (!_ws || _ws.readyState !== 1) {
      return { ok: false, error: "ws_not_open", status: wsStatus() };
    }
    var now = Date.now();
    if (!force && _wsLastSentAt && (now - _wsLastSentAt) < _wsMinIntervalMs) {
      return { ok: true, skipped: true, reason: "rate_limit" };
    }
    try {
      var envelope = {
        type: "telemetry",
        schema: (payload && payload.schemaVersion) || "cornerai-gemini-v1.1",
        ts: now,
        payload: payload
      };
      _ws.send(JSON.stringify(envelope));
      _wsLastSentAt = now;
      _wsSent += 1;
      return { ok: true, sent: _wsSent };
    } catch (e) {
      _wsLastError = e.message || String(e);
      return { ok: false, error: _wsLastError };
    }
  }

  function prepareFromState(state) {
    if (!state || typeof state !== "object") return null;
    var s = state;
    if (typeof root !== "undefined" && root.CornerAILib && typeof root.CornerAILib.pruneFutureEventsList === "function") {
      try {
        s = Object.assign({}, state, {
          cornerEvents: root.CornerAILib.pruneFutureEventsList(
            state.cornerEvents || [],
            state.liveStatus,
            state.minute
          )
        });
      } catch (e) { /* keep original */ }
    }
    return formatPayloadForGemini(s);
  }

  /**
   * Prepara + envia via WS se conectado.
   */
  function pushState(state, force) {
    var payload = prepareFromState(state);
    if (!payload) return { ok: false, error: "invalid_state" };
    return sendViaWebSocket(payload, !!force);
  }

  return {
    formatPayloadForGemini: formatPayloadForGemini,
    sendToGeminiSkill: sendToGeminiSkill,
    prepareFromState: prepareFromState,
    // WebSocket API
    connectWebSocket: connectWebSocket,
    disconnectWebSocket: disconnectWebSocket,
    sendViaWebSocket: sendViaWebSocket,
    pushState: pushState,
    wsStatus: wsStatus,
    onWsEvent: onWsEvent
  };
});
