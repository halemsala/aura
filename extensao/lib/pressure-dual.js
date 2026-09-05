/**
 * Pure: evaluate pressure bar dual integrity (0×N valid).
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function isPressureBarDual(v) {
    if (!v || v.empty) return null;
    var h = Number(v.home), a = Number(v.away), pct = Number(v.pct);
    if (Number.isFinite(h) && Number.isFinite(a) && h >= 0 && a >= 0) return true;
    if (Number.isFinite(pct) && pct >= 0 && pct <= 100) return true;
    return false;
  }
  function evaluatePressureDual(bars) {
    bars = bars && typeof bars === "object" ? bars : {};
    var goodBars = 0, badBars = 0;
    for (var k in bars) {
      if (!Object.prototype.hasOwnProperty.call(bars, k)) continue;
      var dual = isPressureBarDual(bars[k]);
      if (dual === null) continue;
      if (dual) goodBars++; else badBars++;
    }
    var totalBars = goodBars + badBars;
    var ratio = totalBars ? goodBars / totalBars : 1;
    var ok = badBars === 0 || (goodBars >= 3 && ratio >= 0.75);
    return { ok: ok, goodBars: goodBars, badBars: badBars, ratio: ratio };
  }
  return { isPressureBarDual: isPressureBarDual, evaluatePressureDual: evaluatePressureDual };
});
