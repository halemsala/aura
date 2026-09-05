/**
 * Pure: evaluate whether aggregate corner stats (stats.corners) are consistent
 * with the discrete corner event log (cornerEvents), tolerating known,
 * non-corrupting source behaviors from SokkerPRO:
 *
 *  - side-skew: stats and events disagree on WHICH side by <=1 each,
 *    but the TOTAL matches (e.g. stats 4x3 / events 3x4, total 7=7).
 *    This is attribution lag between the aggregate stat and the discrete
 *    event parser, not a data-integrity failure.
 *  - timeline-pending: early in the match (<45'), the aggregate stat can
 *    be ahead of the (lazy/virtualized) event list. This is source
 *    incompleteness, not corruption — never invent synthetic events to
 *    compensate.
 *  - inflated: events exceed stats by more than 1 on either side. This
 *    IS treated as a real problem (phantom/duplicate corner events).
 *
 * Single source of truth shared by background.js (integrity report) and
 * diagnostics.js (review panel) so both never disagree on the same data.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function evaluateCornerAlign(opts) {
    opts = opts || {};
    var sh = Number(opts.statsHome);
    var sa = Number(opts.statsAway);
    var eh = Number(opts.eventsHome) || 0;
    var ea = Number(opts.eventsAway) || 0;
    var liveMinute = Number(opts.liveMinute) || 0;
    var isLive = !!opts.isLive;
    var hasEventChannel = !!opts.hasEventChannel; // e.g. state.diagnostics.hookMessages > 0

    var statsKnown = Number.isFinite(sh) && Number.isFinite(sa);
    var totalStats = statsKnown ? sh + sa : null;
    var totalEvents = eh + ea;
    var totalsMatch = totalStats != null && totalStats === totalEvents;

    var lagH = statsKnown ? sh - eh : 0;
    var lagA = statsKnown ? sa - ea : 0;

    // Tolerate <=1 per-side lag when totals reconcile: attribution skew, not corruption.
    var sideSkew = statsKnown && Math.abs(lagH) <= 1 && Math.abs(lagA) <= 1 && totalsMatch;

    // Events meaningfully outrunning stats on a side = phantom/duplicate events.
    var inflated = statsKnown && !sideSkew && (eh > sh + 1 || ea > sa + 1);

    // Aggregate stat ahead of a lazy/virtualized event list.
    // SokkerPRO frequently updates the stat row 1 tick before the discrete event.
    var earlyPending = statsKnown && totalEvents === 0 && liveMinute < 45 && (totalStats || 0) > 0;
    var partialEarly = statsKnown && totalStats > totalEvents && liveMinute < 45 && totalEvents >= 0 && !hasEventChannel;
    var liveTotalLag = isLive && statsKnown && !inflated &&
      totalStats >= totalEvents && (totalStats - totalEvents) <= 2 &&
      Math.abs(lagH) <= 2 && Math.abs(lagA) <= 2;
    var timelinePending = isLive && (earlyPending || partialEarly || liveTotalLag);

    var exactMatch = statsKnown && sh === eh && sa === ea;
    var aligned = !statsKnown || exactMatch || sideSkew || liveTotalLag;
    var ok = aligned || timelinePending;

    var detail;
    if (timelinePending) {
      detail = "stats " + (statsKnown ? sh : "\u2014") + "\u00d7" + (statsKnown ? sa : "\u2014") +
        " \u00b7 eventos " + eh + "\u00d7" + ea +
        (liveTotalLag && !earlyPending && !partialEarly ? " \u00b7 lag live \u22642 (fonte)" : " \u00b7 timeline pendente");
    } else if (sideSkew && !exactMatch) {
      detail = "stats " + sh + "\u00d7" + sa + " \u00b7 eventos " + eh + "\u00d7" + ea +
        " \u00b7 side-skew OK (total " + totalStats + ")";
    } else {
      detail = "stats " + (statsKnown ? sh : "\u2014") + "\u00d7" + (statsKnown ? sa : "\u2014") +
        " \u00b7 eventos " + eh + "\u00d7" + ea;
    }

    return {
      ok: ok,
      aligned: aligned,
      sideSkew: sideSkew,
      inflated: inflated,
      timelinePending: timelinePending,
      liveTotalLag: !!liveTotalLag,
      exactMatch: !!exactMatch,
      lag: [lagH, lagA],
      totals: [totalStats, totalEvents],
      detail: detail
    };
  }
  return { evaluateCornerAlign: evaluateCornerAlign };
});
