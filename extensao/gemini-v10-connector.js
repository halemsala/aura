/**
 * CornerAI v10 — Gem & Experience Database Connector
 * Replica o comportamento de um Gem (systemInstruction + telemetria)
 * via API oficial generativelanguage.googleapis.com
 *
 * Nota: Gems da UI Google não têm endpoint público próprio.
 * A forma correta é systemInstruction + modelo (flash/pro ou tuned model ID).
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAIGemV10 = Object.assign(root.CornerAIGemV10 || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEFAULT_SYSTEM = [
    "Você é o CornerAI v10 + Experience Database.",
    "Objetivo único: estimar o momento mais provável do PRÓXIMO escan teio (não gols, não vencedor).",
    "Use a telemetria ao vivo (APPM, momentum, xG, cantos, CPI, prediction_2m) e cruze com padrões históricos quando houver.",
    "Regras:",
    "- Nunca invente estatísticas ausentes.",
    "- Diferencie observado vs inferido.",
    "- Janelas oficiais: W1 30-48' | W2 80-95'+.",
    "- Fora das janelas: prefira AGUARDA / NÃO ENTRA salvo sequência ≤4 min.",
    "- Kill zones: placar ≥2, gol recente ≤3 min, pressão estéril, 0-0 pós-85' com xG dominante (risco de gol).",
    "Resposta OBRIGATÓRIA em JSON estrito (sem markdown):",
    '{"action":"ENTRA|AGUARDA|NAO_ENTRA","side":"home|away|null","minute_pred":null_or_int,"confidence":0-100,',
    '"pressure":"1 frase","experience":"1 frase padrão histórico","risk":"Baixo|Medio|Alto","reason":"1-2 frases","kills":[]}'
  ].join("\n");

  function buildPromptFromPayload(payload) {
    if (!payload) return "";
    var mc = payload.matchContext || {};
    var ts = payload.telemetryStats || {};
    var mom = payload.momentum || {};
    var intel = payload.intelligence || {};
    var cpi = intel.CPI_v2 || {};
    var pred = intel.prediction_corner_2m || {};
    var recent = (payload.events && payload.events.recentCorners) || [];
    var market = payload.market || {};

    function pair(obj, a, b) {
      obj = obj || {};
      return (obj[a] != null ? obj[a] : "—") + " × " + (obj[b] != null ? obj[b] : "—");
    }

    var lines = [
      "=== TELEMETRIA AO VIVO CornerAI v10 ===",
      "Schema: " + (payload.schemaVersion || "n/a"),
      "Fixture: " + (mc.fixtureId || "n/a"),
      "Jogo: " + (mc.homeTeam || "?") + " vs " + (mc.awayTeam || "?"),
      "Placar: " + pair(mc.score, "home", "away"),
      "Relógio: " + ((mc.clock && mc.clock.display) || "?") + " · status=" + ((mc.clock && mc.clock.status) || "?"),
      "",
      "[STATS]",
      "Escanteios: " + pair(ts.corners, "home", "away"),
      "AP (dangerous): " + pair(ts.dangerousAttacks, "home", "away"),
      "Chutes no alvo: " + pair(ts.shotsOnTarget, "home", "away"),
      "xG: " + pair(ts.xg, "home", "away"),
      "Posse: " + pair(ts.possession, "home", "away"),
      "APPM: " + JSON.stringify(ts.appm || {}),
      "",
      "[MOMENTUM]",
      "Home: " + (mom.home != null ? mom.home : "—") + " | Away: " + (mom.away != null ? mom.away : "—"),
      "Readiness: " + (mom.readinessScore != null ? mom.readinessScore : "—") + " | Quality: " + (mom.dataQualityScore != null ? mom.dataQualityScore : "—"),
      "",
      "[INTELLIGENCE]",
      "CPI_v2: " + JSON.stringify(cpi),
      "prediction_corner_2m: " + JSON.stringify(pred),
      "pressureBarsRecent: " + JSON.stringify(intel.pressureBarsRecent || null),
      "",
      "[MARKET]",
      "cornersOdds: " + JSON.stringify(market.cornersOdds || null),
      "1x2: " + JSON.stringify(market.oneXTwo || null),
      "",
      "[RECENT CORNERS]",
      recent.length ? recent.map(function (c) {
        return (c.minute != null ? c.minute : "?") + "' " + (c.side || "?") + " " + (c.period || "");
      }).join(" | ") : "(nenhum)",
      "",
      "Consulte a Experience Database mental (padrões W1/W2, sequência, pressão lateral) e responda no JSON obrigatório."
    ];
    return lines.join("\n");
  }

  /**
   * Chama a API Gemini (Gem-like) com systemInstruction.
   * @param {Object} opts
   * @param {string} opts.apiKey
   * @param {string} [opts.model]
   * @param {string} [opts.systemInstruction]
   * @param {Object} opts.payload - cornerai-gemini-v1.1
   * @param {number} [opts.temperature]
   * @param {number} [opts.maxOutputTokens]
   */
  async function analyzeWithGemV10(opts) {
    opts = opts || {};
    var apiKey = opts.apiKey;
    if (!apiKey) return { ok: false, error: "api_key_missing" };

    var model = opts.model || "gemini-2.0-flash";
    var systemInstruction = opts.systemInstruction || DEFAULT_SYSTEM;
    var payload = opts.payload;
    if (!payload) return { ok: false, error: "payload_missing" };

    var promptText = buildPromptFromPayload(payload);
    var url = "https://generativelanguage.googleapis.com/v1beta/models/" +
      encodeURIComponent(model) + ":generateContent?key=" + encodeURIComponent(apiKey);

    var body = {
      system_instruction: { parts: [{ text: systemInstruction }] },
      contents: [{ role: "user", parts: [{ text: promptText }] }],
      generationConfig: {
        temperature: opts.temperature != null ? Number(opts.temperature) : 0.2,
        maxOutputTokens: opts.maxOutputTokens != null ? Number(opts.maxOutputTokens) : 500,
        responseMimeType: "application/json"
      }
    };

    try {
      var response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        var msg = (data.error && data.error.message) || ("HTTP " + response.status);
        return { ok: false, error: msg, status: response.status, raw: data };
      }
      var text = "";
      try {
        text = data.candidates[0].content.parts[0].text || "";
      } catch (e) {
        return { ok: false, error: "empty_candidates", raw: data };
      }
      var parsed = null;
      try { parsed = JSON.parse(text); } catch (e) { parsed = null; }
      return {
        ok: true,
        analysis: parsed || text,
        text: text,
        model: model,
        usage: data.usageMetadata || null
      };
    } catch (err) {
      return { ok: false, error: err.message || String(err) };
    }
  }

  return {
    DEFAULT_SYSTEM: DEFAULT_SYSTEM,
    buildPromptFromPayload: buildPromptFromPayload,
    analyzeWithGemV10: analyzeWithGemV10
  };
});
