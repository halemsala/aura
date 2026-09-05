/* AURA local API fallback — inert by default.
 * Same-origin on :8766: the matriz proxy handles /api/aura/* and tRPC.
 * This file only normalizes tRPC batch envelopes so C.data is always an array.
 */
(function () {
  "use strict";
  var host = String(window.location.hostname || "").toLowerCase();
  var port = String(window.location.port || "");
  var isFallback = (host === "127.0.0.1" || host === "localhost") && (port === "8766" || port === "");
  if (!isFallback || !window.fetch) return;

  if (location.pathname === "/index.html" || location.pathname === "/index.htm") {
    try { history.replaceState(null, "", "/" + location.search + location.hash); } catch (_) {}
  }

  function asArray(value) {
    if (Array.isArray(value)) return value;
    if (value && Array.isArray(value.items)) return value.items;
    if (value && Array.isArray(value.json)) return value.json;
    return [];
  }

  function normalizeTrpc(data) {
    if (Array.isArray(data)) {
      return data.map(function (item) { return normalizeTrpc(item); });
    }
    if (!data || typeof data !== "object") return data;
    var node = data.result && data.result.data;
    if (node && !Array.isArray(node) && node.json !== undefined) {
      if (!Array.isArray(node.json)) node.json = asArray(node.json);
    } else if (node && !Array.isArray(node)) {
      data.result.data = { json: asArray(node) };
    }
    return data;
  }

  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var raw = typeof input === "string" ? input : (input && input.url) || "";
    var parsed;
    try { parsed = new URL(raw, window.location.href); } catch (_) { return nativeFetch(input, init); }
    if (parsed.pathname.indexOf("/api/trpc") !== 0) return nativeFetch(input, init);
    return nativeFetch(input, init).then(function (resp) {
      return resp.clone().json().then(function (data) {
        try { data = normalizeTrpc(data); } catch (_) {}
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }).catch(function () { return resp; });
    });
  };
})();
