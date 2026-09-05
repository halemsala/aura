/**
 * Pure: reject future events vs live clock (+2 tolerance).
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function eventWithinClock(e, liveStatus, clockMinute) {
    if (String(liveStatus || "") !== "live") return true;
    var clock = Number(clockMinute);
    if (!Number.isFinite(clock)) return true;
    var m = Number(e && e.minute);
    if (!Number.isFinite(m)) return true;
    if (m > clock + 2) return false;
    if (m > 130) return false;
    return true;
  }
  function pruneFutureEventsList(events, liveStatus, clockMinute) {
    var list = Array.isArray(events) ? events : [];
    return list.filter(function (e) { return eventWithinClock(e, liveStatus, clockMinute); });
  }
  return { eventWithinClock: eventWithinClock, pruneFutureEventsList: pruneFutureEventsList };
});
