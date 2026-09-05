(function(){
  if (window.__AURA_TOOLS_RAIL_V3__) return;
  window.__AURA_TOOLS_RAIL_V3__ = true;
  function clickLabel(label){
    var nodes = document.querySelectorAll("[data-label], .dock-item, .ribbon-button, button, a, [role=button]");
    for (var i=0;i<nodes.length;i++){
      var n = nodes[i];
      var t = (n.getAttribute("data-label")||n.getAttribute("aria-label")||n.textContent||"").trim();
      if (t && t.toLowerCase().indexOf(label.toLowerCase())>=0){ try{n.click(); return true;}catch(e){} }
    }
    return false;
  }
  function mount(){
    var old = document.getElementById("aura-tools-rail");
    if (old && old.getAttribute("data-v")==="3") return;
    if (old) old.remove();
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "./assets/aura-tools-rail.css";
    document.head.appendChild(link);
    var box = document.createElement("div");
    box.id = "aura-tools-rail";
    box.setAttribute("data-v","3");
    box.innerHTML =
      '<div class="rail-title">Controlo</div>'+
      '<a class="rail-btn accent" href="./tools-hub.html">Painel Controlo</a>'+
      '<button type="button" data-k="atlas">Atlas</button>'+
      '<button type="button" data-k="agentes">Agentes</button>'+
      '<button type="button" data-k="ferramentas">Ferramentas</button>'+
      '<button type="button" data-k="diagnostico">Diagnóstico</button>'+
      '<button type="button" data-k="voz">Voz</button>'+
      '<button type="button" data-k="sistema">Sistema</button>'+
      '<a class="rail-btn" href="http://127.0.0.1:8080/health" target="_blank" rel="noopener">Bridge</a>'+
      '<a class="rail-btn" href="http://127.0.0.1:8765/api/health" target="_blank" rel="noopener">Engine</a>'+
      '<a class="rail-btn" href="http://127.0.0.1:8099/api/voice/health" target="_blank" rel="noopener">Voice</a>'+
      '<a class="rail-btn" href="http://127.0.0.1:8790/health" target="_blank" rel="noopener">Ctrl API</a>';
    box.addEventListener("click", function(ev){
      var b = ev.target.closest("button"); if(!b) return;
      var map = {atlas:"Atlas",agentes:"Agentes",ferramentas:"Ferramentas",diagnostico:"Diagn",voz:"Voz",sistema:"Sistema"};
      clickLabel(map[b.getAttribute("data-k")]||b.textContent);
    });
    document.body.appendChild(box);
    if (!document.getElementById("aura-tools-hub-fab")){
      var fab = document.createElement("button");
      fab.id = "aura-tools-hub-fab";
      fab.type = "button";
      fab.textContent = "Controlo";
      fab.onclick = function(){ window.location.href = "./tools-hub.html"; };
      document.body.appendChild(fab);
    }
  }
  if (document.readyState === "complete" || document.readyState === "interactive") setTimeout(mount, 350);
  else window.addEventListener("DOMContentLoaded", function(){ setTimeout(mount, 350); });
  window.addEventListener("load", function(){ setTimeout(mount, 700); });
})();
