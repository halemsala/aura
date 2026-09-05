/* Botão Falar — grava o microfone do Windows (Realtek) no PC, não no browser. */
(function () {
  if (window.__AURA_MIC__) return;
  window.__AURA_MIC__ = true;
  var API = "http://127.0.0.1:8777";
  function toast(t) {
    var el = document.getElementById("aura-mic-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "aura-mic-toast";
      el.style.cssText = "position:fixed;bottom:72px;right:16px;z-index:9999;max-width:320px;background:#111;color:#eee;padding:10px 12px;border-radius:10px;font:13px sans-serif;";
      document.body.appendChild(el);
    }
    el.textContent = t;
  }
  async function talk() {
    var b = document.getElementById("aura-mic-btn");
    try {
      b.textContent = "A ouvir 8s…";
      toast("Pode falar. Estou a gravar 8 segundos no microfone do Windows (Realtek).");
      var ac = new AbortController();
      var to = setTimeout(function () { ac.abort(); }, 90000);
      var r = await fetch(API + "/api/listen", {
        method: "POST",
        cache: "no-store",
        signal: ac.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seconds: 8, prefer: "realtek" })
      });
      clearTimeout(to);
      var d = await r.json();
      b.textContent = "Falar";
      var t = String(d.text || "").trim();
      var rms = Number(d.rms || 0);
      var dev = d.device || "Windows";
      if (d.silent || (rms > 0 && rms < 0.008)) {
        toast("O microfone " + dev + " está em silêncio. Som → Entrada → Conjunto de microfones Realtek.");
        return;
      }
      if (!t) {
        toast("Gravei o " + dev + " mas não percebi fala. Mais alto e mais perto.");
        return;
      }
      if (!/^alfred\b/i.test(t)) t = "Alfred, " + t;
      toast("Ouvi: " + t);
      await fetch(API + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: t, use_memory: true })
      });
    } catch (e) {
      b.textContent = "Falar";
      toast("Microfone: " + String(e.message || e));
    }
  }
  function mount() {
    if (document.getElementById("aura-mic-btn")) return;
    var b = document.createElement("button");
    b.id = "aura-mic-btn";
    b.type = "button";
    b.textContent = "Falar";
    b.style.cssText = "position:fixed;bottom:16px;right:16px;z-index:9999;background:#1f6feb;color:#fff;border:0;border-radius:999px;padding:12px 18px;font:700 14px sans-serif;cursor:pointer;box-shadow:0 8px 24px #0008";
    b.onclick = talk;
    document.body.appendChild(b);
  }
  if (document.readyState === "complete") mount();
  else window.addEventListener("load", mount);
})();
