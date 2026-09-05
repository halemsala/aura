(function () {
  "use strict";
  const CORE = "http://127.0.0.1:8088";
  const KEYS = ["odds", "corner", "xG", "pressure", "momentum", "score", "minute"];
  function scan() {
    const text = (document.body && document.body.innerText) || "";
    const wom = { home: 0.5, away: 0.5, ts: Date.now() };
    const mHome = text.match(/home[^0-9]{0,12}(\d+\.?\d*)/i);
    const mAway = text.match(/away[^0-9]{0,12}(\d+\.?\d*)/i);
    if (mHome) wom.home = Math.min(1, parseFloat(mHome[1]) / 100 || parseFloat(mHome[1]));
    if (mAway) wom.away = Math.min(1, parseFloat(mAway[1]) / 100 || parseFloat(mAway[1]));
    const payload = {
      texto: KEYS.map(k => (text.toLowerCase().includes(k.toLowerCase()) ? k : "")).filter(Boolean).join(" ") || "trading live market",
      estado_hash: String(wom.ts)
    };
    fetch(CORE + "/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).catch(() => {});
    fetch(CORE + "/api/twin_sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prob: (wom.home + (1 - wom.away)) / 2,
        momentum: Math.abs(wom.home - wom.away),
        pressure: wom.home
      })
    }).catch(() => {});
  }
  setInterval(scan, 3000);
  scan();
})();
