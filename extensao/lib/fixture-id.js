/**
 * Pure: extract fixture ID from URL / string.
 * UMD — works in content script, service worker, and Node/Jest.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function extractFidFromString(s) {
    try {
      var str = String(s || "");
      if (/^\d{5,12}$/.test(str.trim())) return str.trim();
      var m = str.match(/\/(?:fixture|partida|match|game|event)\/(\d{5,})/i);
      if (m) return m[1];
      m = str.match(/[?&#](?:fixture|fixtureId|matchId|match_id|gameId|game_id|eventId)=(\d{5,})/i);
      if (m) return m[1];
      m = str.match(/\/ws\/fixture\/(\d{5,})/i);
      if (m) return m[1];
      m = str.match(/\/(?:api\/)?fixtures?\/(\d{5,})/i);
      if (m) return m[1];
      m = str.match(/["'](?:fixture(?:Id)?|matchId|gameId)["']\s*[:=]\s*["']?(\d{5,})/i);
      if (m) return m[1];
      m = str.match(/sokkerpro\.com\/(?:fixture\/)?(\d{6,})(?:\/|$|\?)/i);
      if (m) return m[1];
      return null;
    } catch (e) {
      return null;
    }
  }
  return { extractFidFromString: extractFidFromString };
});
