/**
 * Pure text-chunk reassembly (mirrors page-hook appendTextChunk policy).
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var MAX_BYTES = 2 * 1024 * 1024;
  var FLUSH_MS = 80;

  function createChunkStore() {
    return new Map();
  }

  function appendTextChunk(store, endpoint, chunk, now) {
    now = now || Date.now();
    var text = String(chunk || "");
    if (!endpoint || !text) return { action: "skip" };
    var entry = store.get(endpoint);
    if (!entry) {
      entry = { buf: "", bytes: 0, parts: 0, firstAt: now, lastAt: now };
      store.set(endpoint, entry);
    }
    entry.buf += text;
    entry.bytes += text.length;
    entry.parts += 1;
    entry.lastAt = now;
    if (entry.bytes > MAX_BYTES) {
      store.delete(endpoint);
      return { action: "overflow", bytes: entry.bytes };
    }
    // try complete JSON
    try {
      JSON.parse(entry.buf);
      store.delete(endpoint);
      return { action: "complete", text: entry.buf, parts: entry.parts };
    } catch (e) {}
    return { action: "buffered", parts: entry.parts, bytes: entry.bytes };
  }

  function flushChunkBuffer(store, endpoint, reason) {
    var entry = store.get(endpoint);
    if (!entry) return null;
    store.delete(endpoint);
    return { text: entry.buf, parts: entry.parts, bytes: entry.bytes, reason: reason || "flush" };
  }

  function shouldFlushByAge(entry, now, maxAgeMs) {
    maxAgeMs = maxAgeMs || FLUSH_MS;
    now = now || Date.now();
    return entry && now - entry.firstAt >= maxAgeMs;
  }

  return {
    createChunkStore: createChunkStore,
    appendTextChunk: appendTextChunk,
    flushChunkBuffer: flushChunkBuffer,
    shouldFlushByAge: shouldFlushByAge,
    CHUNK_MAX_BYTES: MAX_BYTES,
    CHUNK_FLUSH_MS: FLUSH_MS
  };
});
