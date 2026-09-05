/**
 * Pure: parse football clock strings (45', 45+2', HT, FT).
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function parseClockText(text) {
    var t = String(text || "").replace(/\s+/g, " ").trim();
    if (!t || t.length > 32) return null;
    if (/escanteio|canto|corner|gol\b|goal|cart[aã]o|substit/i.test(t)) return null;
    var m = t.match(/^(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?$/);
    if (m) {
      var minute = Number(m[1]);
      var extra = Number(m[2]);
      if (minute >= 0 && minute <= 130) return { minute: minute, extraMinute: extra, display: minute + "+" + extra + "'" };
    }
    m = t.match(/^(\d{1,3})\s*['′]?$/);
    if (m) {
      minute = Number(m[1]);
      if (minute >= 0 && minute <= 130) return { minute: minute, extraMinute: 0, display: minute + "'" };
    }
    m = t.match(/\b(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?/);
    if (m) {
      minute = Number(m[1]);
      extra = Number(m[2]);
      if (minute >= 0 && minute <= 130) return { minute: minute, extraMinute: extra, display: minute + "+" + extra + "'" };
    }
    m = t.match(/\b(\d{1,3})\s*['′](?!\s*\d)/);
    if (m) {
      minute = Number(m[1]);
      if (minute >= 0 && minute <= 130) return { minute: minute, extraMinute: 0, display: minute + "'" };
    }
    return null;
  }
  function pickBestClock(candidates) {
    if (!Array.isArray(candidates) || !candidates.length) return null;
    var ranked = candidates
      .filter(function (c) { return c && Number.isFinite(c.minute) && c.minute >= 0 && c.minute <= 130; })
      .sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
    return ranked[0] || null;
  }
  return { parseClockText: parseClockText, pickBestClock: pickBestClock };
});
