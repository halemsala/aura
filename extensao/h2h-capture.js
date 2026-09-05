(() => {
if(window.__cornerAIH2HV69191)return;window.__cornerAIH2HV69191=true;
  "use strict";
  const VERSION="12.8.9";
  const PREFIX = "[CornerAI H2H]";
  let lastHash = "";
  let lastSent = 0;
  let attemptedAt = 0;
  let scheduled = 0;
  let captureArmed = true; // FORCE_H2H_ON 12.8.14

  const clean = v => String(v ?? "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const norm = v => clean(v).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const fixtureId = () => {
    try {
      const u = new URL(location.href);
      return u.searchParams.get("fixture") || ((u.pathname.match(/\/(?:fixture|partida|match|game)\/(\d+)/i) || [])[1] || null);
    } catch { return null; }
  };
  const nums = s => (String(s || "").match(/-?\d+(?:[.,]\d+)?/g) || []).map(x => Number(String(x).replace(",", "."))).filter(Number.isFinite);
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function send(type, payload) {
    return new Promise(resolve => {
      try {
        chrome.runtime.sendMessage({ type, payload }, r => {
          const err = chrome.runtime.lastError;
          if (err) return resolve({ ok: false, error: err.message });
          resolve(r || { ok: true });
        });
      } catch (e) {
        resolve({ ok: false, error: e?.message || String(e) });
      }
    });
  }

  function score(el) {
    const t = norm(el?.innerText || el?.textContent || el?.getAttribute?.("aria-label") || el?.title || el?.getAttribute?.("data-tab") || "");
    let s = 0;
    if (/\bh2h\b/.test(t)) s += 14;
    if (/head\s*to\s*head/.test(t)) s += 12;
    if (/confront/.test(t)) s += 10;
    if (/frente a frente/.test(t)) s += 9;
    if (/resultados?\s*\(\d+\)/.test(t)) s += 8;
    if (/historico|histórico/.test(t)) s += 6;
    if (/ultimos jogos|últimos jogos|last matches/.test(t)) s += 5;
    if (/comparativo|comparison/.test(t)) s += 4;
    return s;
  }

  const SCORE_RE = /(\d{1,2})\s*[-–—−~:xX×]\s*(\d{1,2})/;

  function findH2HRoot() {
    const candidates = [...document.querySelectorAll("section,article,div,main,[class*='h2h'],[class*='confront']")];
    let best = null;
    for (const el of candidates) {
      const t = clean(el.innerText || "").slice(0, 6000);
      if (t.length < 40) continue;
      const n = norm(t);
      const hasLabel = /\bh2h\b/.test(n) || /head\s*to\s*head/.test(n) || /frente a frente/.test(n) || /confrontos/.test(n);
      const hasResults = /resultados\s*\(\d+\)/.test(n) || (/vit[oó]rias/.test(n) && /empates/.test(n));
      const scoreHits = (t.match(new RegExp(SCORE_RE.source, "g")) || []).length;
      if (!hasLabel && !hasResults && scoreHits < 5) continue;
      if (!hasLabel && scoreHits < 8) continue;
      const tables = el.querySelectorAll("table").length;
      const scoreVal = (hasLabel ? 6 : 0) + (hasResults ? 4 : 0) + Math.min(5, scoreHits) + (tables > 0 ? 2 : 0);
      // Prefer smaller containers with strong signal (avoid whole page).
      const sizePenalty = Math.min(3, Math.floor(t.length / 4000));
      const final = scoreVal - sizePenalty;
      if (!best || final > best.score) best = { el, score: final, text: t };
    }
    return best?.el || null;
  }

  function parseSummary(root) {
    // Aceita: Element/Document | string | { innerText|text } — nunca assume querySelectorAll
    let text = "";
    let domRoot = null;
    if (typeof root === "string") {
      text = clean(root);
    } else if (root && typeof root === "object" && !(root.querySelectorAll)) {
      text = clean(root.innerText || root.text || root.textContent || "");
    } else {
      domRoot = root && root.querySelectorAll ? root : document;
      try {
        text = clean((root && root.innerText != null ? root.innerText : (document.body?.innerText || "")) || "");
      } catch {
        text = clean(document.body?.innerText || "");
      }
    }
    const summary = { homeWins: null, draws: null, awayWins: null, total: null };
    const compact = text.replace(/\s+/g, " ");
    // Patterns seen on SokkerPRO H2H banner
    const patterns = [
      /(\d+)\s*vit[oó]rias?\s+(\d+)\s*empates?\s+(\d+)\s*vit[oó]rias?/i,
      /(\d+)\s*wins?\s+(\d+)\s*draws?\s+(\d+)\s*wins?/i,
      /(\d+)\s*v\s+(\d+)\s*e\s+(\d+)\s*v\b/i
    ];
    let m = null;
    for (const re of patterns) { m = compact.match(re); if (m) break; }
    if (!m) {
      const wins = [...compact.matchAll(/(\d+)\s*vit[oó]rias?/gi)].map(x => Number(x[1]));
      const draws = [...compact.matchAll(/(\d+)\s*empates?/gi)].map(x => Number(x[1]));
      if (wins.length >= 2 && draws.length >= 1) m = [null, String(wins[0]), String(draws[0]), String(wins[1])];
    }
    // DOM nodes: three metric blocks near "vitórias/empates" (só se root for Element)
    if (!m && domRoot && typeof domRoot.querySelectorAll === "function") {
      let nodes = [];
      try {
        nodes = [...domRoot.querySelectorAll("div,span,strong,b,p,li")];
      } catch {
        nodes = [];
      }
      const vals = [];
      for (const el of nodes) {
        const t = clean(el.textContent || "");
        if (t.length > 40) continue;
        const vm = t.match(/^(\d{1,2})\s*vit[oó]rias?$/i);
        const dm = t.match(/^(\d{1,2})\s*empates?$/i);
        if (vm) vals.push({ k: "w", n: Number(vm[1]) });
        if (dm) vals.push({ k: "d", n: Number(dm[1]) });
      }
      for (let i = 0; i < vals.length - 2; i++) {
        if (vals[i].k === "w" && vals[i+1].k === "d" && vals[i+2].k === "w") {
          m = [null, String(vals[i].n), String(vals[i+1].n), String(vals[i+2].n)];
          break;
        }
      }
    }
    if (m) {
      const hw = Number(m[1]), dr = Number(m[2]), aw = Number(m[3]);
      // 9.2.7: discard absurd league-table contamination (e.g. homeWins 12613)
      if (Number.isFinite(hw) && Number.isFinite(dr) && Number.isFinite(aw)
          && hw >= 0 && aw >= 0 && dr >= 0 && hw <= 40 && aw <= 40 && dr <= 40
          && (hw + dr + aw) <= 80) {
        summary.homeWins = hw;
        summary.draws = dr;
        summary.awayWins = aw;
        summary.total = hw + dr + aw;
      }
    }
    const totalM = compact.match(/resultados?\s*\((\d+)\)/i);
    if (totalM) {
      const t = Number(totalM[1]);
      if (Number.isFinite(t) && t > 0 && t <= 80) summary.total = t;
    }
    return summary;
  }

  function parseMatchRow(cells) {
    if (!cells || !cells.length) return null;
    let joined = cells.map(clean).filter(Boolean);
    if (!joined.length) return null;
    // Ignore pure header rows
    const headerish = joined.filter(c => /^(data|campeonato|casa|fora|placar|home|away|score|date|jogo|match)$/i.test(c)).length;
    if (headerish >= 2) return null;
    // Ignore pure metric rows (média de gols, etc.) without team names
    const blob0 = joined.join(" ");
    if (/^(m[eé]dia|avg|taxa|rate|over|under|btts|posse|xg)\b/i.test(blob0) && !SCORE_RE.test(blob0)) return null;

    // Merge split score cells: ["0","-","1"] or ["0","1"] between team columns
    const merged = [];
    for (let i = 0; i < joined.length; i++) {
      const a = joined[i], b = joined[i+1], c = joined[i+2];
      if (/^\d{1,2}$/.test(a) && b && /^[-–—−~:xX×]$/.test(b) && c && /^\d{1,2}$/.test(c)) {
        merged.push(a + "-" + c); i += 2; continue;
      }
      if (/^\d{1,2}$/.test(a) && b && /^\d{1,2}$/.test(b) && !/[a-zA-Zà-úÀ-Ú]/.test(a) && !/[a-zA-Zà-úÀ-Ú]/.test(b)) {
        const prev = merged[merged.length-1] || "";
        const next = joined[i+2] || "";
        if (/[a-zA-Zà-úÀ-Ú]/.test(prev) || /[a-zA-Zà-úÀ-Ú]/.test(next)) {
          merged.push(a + "-" + b); i += 1; continue;
        }
      }
      merged.push(a);
    }
    joined = merged;

    const blob = joined.join(" ");
    // Prefer a cell that is ONLY a score (short)
    let scoreIdx = joined.findIndex(c => {
      const cc = clean(c);
      return SCORE_RE.test(cc) && cc.replace(SCORE_RE, "").trim().length === 0 && cc.length <= 12;
    });
    let sm = null, home = "", away = "", date = "", competition = "";
    if (scoreIdx >= 0) {
      sm = joined[scoreIdx].match(SCORE_RE);
      home = joined[scoreIdx - 1] || "";
      away = joined[scoreIdx + 1] || "";
      // Se home ainda tem placar embutido ou date, tenta células anteriores
      if (!home || /^\d+$/.test(home)) home = joined[scoreIdx - 2] || home;
      if (!away || /^\d+$/.test(away)) away = joined[scoreIdx + 2] || away;
      date = joined.find(c => /^\d{1,2}\/\d{1,2}(?:\/\d{2,4})?$/.test(c)) || joined[0] || "";
      competition = joined.find((c, i) => i > 0 && i < scoreIdx - 1 && /[a-zA-Zà-úÀ-Ú]/.test(c) && c !== home) || "";
    } else {
      const all = [...blob.matchAll(new RegExp(SCORE_RE.source, "g"))];
      // Prefer score not part of a date (dd/mm/yy uses /)
      sm = null;
      for (let i = all.length - 1; i >= 0; i--) {
        const cand = all[i];
        const around = blob.slice(Math.max(0, cand.index - 3), cand.index + cand[0].length + 3);
        if (/\d\/\d/.test(around) && !/[-–xX×]/.test(cand[0])) continue;
        sm = cand;
        break;
      }
      if (!sm && all.length) sm = all[all.length - 1];
      if (!sm) return null;
      const before = clean(blob.slice(0, sm.index).replace(/\|\s*$/, ""));
      const after = clean(blob.slice(sm.index + sm[0].length).replace(/^\s*\|/, ""));
      const beforeParts = before.split(/\s*\|\s*/).map(clean).filter(Boolean);
      const afterParts = after.split(/\s*\|\s*/).map(clean).filter(Boolean);
      home = beforeParts[beforeParts.length - 1] || "";
      away = afterParts[0] || "";
      date = beforeParts.find(p => /^\d{1,2}\/\d{1,2}/.test(p)) || beforeParts[0] || "";
      competition = beforeParts.length >= 3 ? beforeParts[1] : (beforeParts.length >= 2 ? beforeParts[0] : "");
      const dm = home.match(/^(\d{1,2}\/\d{1,2}\/\d{2,4})\s+(.+)$/);
      if (dm) { date = dm[1]; home = clean(dm[2]); }
      // Fallback: split before by spaces for "21/12/25 Liga TeamName"
      if ((!home || home.length < 2) && before) {
        const words = before.split(/\s+/).filter(Boolean);
        if (words.length >= 2) {
          date = words[0].match(/^\d{1,2}\/\d{1,2}/) ? words[0] : date;
          home = words.slice(words[0].match(/^\d{1,2}\/\d{1,2}/) ? 1 : 0).join(" ");
          // Se home ficou muito longo, pega últimas 2-4 palavras
          const hw = home.split(/\s+/);
          if (hw.length > 5) {
            competition = hw.slice(0, -3).join(" ");
            home = hw.slice(-3).join(" ");
          }
        }
      }
      if ((!away || away.length < 2) && after) {
        const aw = after.split(/\s+/).filter(Boolean);
        away = aw.slice(0, Math.min(4, aw.length)).join(" ");
      }
    }
    if (!sm) return null;
    const hg = Number(sm[1]), ag = Number(sm[2]);
    if (!Number.isFinite(hg) || !Number.isFinite(ag) || hg < 0 || ag < 0 || hg > 15 || ag > 15) return null;
    home = clean(home); away = clean(away);
    home = home.replace(/\s+\d+$/, "").replace(/^\d+\s+/, "").trim();
    away = away.replace(/^\d+\s+/, "").replace(/\s+\d+$/, "").trim();
    // Remove competition leftovers from team names
    home = home.replace(/^(?:S[eé]rie\s*[A-D]|Bundesliga|Liga|Cup|Copa)\s+/i, "").trim();
    if (!home || home.length < 2 || !away || away.length < 2) return null;
    if (/^(data|campeonato|casa|fora|placar|home|away|score)$/i.test(home) || /^(data|campeonato|casa|fora|placar|home|away|score)$/i.test(away)) return null;
    if (/\d{1,2}\/\d{1,2}/.test(home) || /\d{1,2}\/\d{1,2}/.test(away)) return null;
    // Reject if both "teams" are pure numbers
    if (/^\d+$/.test(home) || /^\d+$/.test(away)) return null;
    return { date: clean(date), competition: clean(competition), home, away, homeGoals: hg, awayGoals: ag, score: hg + "-" + ag };
  }

  function parseMatchesFromText(text) {
    // Fallback when DOM is not a real <table>: parse lines like
    // "21/12/25 Série A Juventude 0 - 1 Flamengo"
    const out = [];
    const seen = new Set();
    const lines = String(text || "").split(/\n+/).map(clean).filter(l => l.length > 8 && l.length < 180);
    const scoreRe = SCORE_RE;
    for (const line of lines) {
      if (!scoreRe.test(line)) continue;
      if (/vit[oó]rias|empates|resultados?\s*\(/i.test(line)) continue;
      const sm = line.match(scoreRe);
      if (!sm) continue;
      const before = clean(line.slice(0, sm.index));
      const after = clean(line.slice(sm.index + sm[0].length));
      // date at start dd/mm/yy
      const dateM = before.match(/^(\d{1,2}\/\d{1,2}\/\d{2,4})\s*(.*)$/);
      let date = "", rest = before, home = "", competition = "";
      if (dateM) { date = dateM[1]; rest = clean(dateM[2]); }
      // last token(s) before score = home team; competition is middle
      const tokens = rest.split(/\s{2,}|\s\|\s/).map(clean).filter(Boolean);
      if (tokens.length >= 2) {
        home = tokens[tokens.length - 1];
        competition = tokens.slice(0, -1).join(" ");
      } else {
        // single spaced: take last 1-3 words as team heuristically
        const words = rest.split(/\s+/).filter(Boolean);
        if (words.length >= 2) {
          home = words.slice(-2).join(" ");
          competition = words.slice(0, -2).join(" ");
          if (!competition && words.length >= 1) { home = words[words.length - 1]; competition = words.slice(0, -1).join(" "); }
        } else home = rest;
      }
      const away = after.split(/\s{2,}|\s\|\s/)[0] || after.split(/\s+/).slice(0, 3).join(" ");
      if (!home || !away) continue;
      const key = date + "|" + home + "|" + sm[1] + "-" + sm[2] + "|" + away;
      if (seen.has(key)) continue;
      seen.add(key);
      const hg = Number(sm[1]), ag = Number(sm[2]);
      if (!Number.isFinite(hg) || !Number.isFinite(ag) || hg > 7 || ag > 7 || hg < 0 || ag < 0) continue;
      const hh = clean(home), aa = clean(away);
      if (!hh || hh.length < 2 || !aa || aa.length < 2) continue;
      if (/\d{1,2}\/\d{1,2}/.test(hh) || /\d{1,2}\/\d{1,2}/.test(aa)) continue;
      out.push({
        date, competition, home: hh, away: aa,
        homeGoals: hg, awayGoals: ag,
        score: hg + "-" + ag
      });
    }
    return out.slice(0, 60);
  }

  function extractTables(root) {
    const scope = root || document;
    const tables = [...scope.querySelectorAll("table")].map((t, index) => {
      const headers = [...t.querySelectorAll("thead th,thead td,tr:first-child th")].map(x => clean(x.textContent)).filter(Boolean).slice(0, 12);
      const rows = [...t.querySelectorAll("tbody tr, tr")].map(tr => [...tr.querySelectorAll("th,td")].map(td => clean(td.textContent))).filter(r => r.length >= 2);
      return { index, headers, rows: rows.slice(0, 80), text: clean(t.innerText || "").slice(0, 8000) };
    }).filter(t => t.rows.length);

    // Div/grid layouts (SokkerPRO sometimes renders H2H without <table>)
    if (!tables.length || tables.every(t => t.rows.every(r => !r.some(c => /\d{1,2}\s*[-–—−~xX]\s*\d{1,2}/.test(c))))) {
      const rowNodes = [...scope.querySelectorAll("[class*='row'],[class*='match'],[class*='result'],li,article")];
      const synthetic = [];
      for (const el of rowNodes) {
        const line = clean(el.innerText || "");
        if (line.length < 10 || line.length > 200) continue;
        if (!/\d{1,2}\s*[-–—−~xX]\s*\d{1,2}/.test(line)) continue;
        if (/vit[oó]rias|empates|resultados?\s*\(/i.test(line)) continue;
        // Split by newline or 2+ spaces into pseudo-cells
        let cells = line.split(/\n+/).map(clean).filter(Boolean);
        if (cells.length < 3) cells = line.split(/\s{2,}/).map(clean).filter(Boolean);
        if (cells.length < 3) {
          // Keep as single blob — parseMatchRow/text parser handles it
          cells = [line];
        }
        synthetic.push(cells);
      }
      if (synthetic.length) {
        tables.push({
          index: tables.length,
          headers: ["Data", "Campeonato", "Casa", "Placar", "Fora"],
          rows: synthetic.slice(0, 80),
          text: synthetic.slice(0, 20).map(r => r.join(" ")).join("\n")
        });
      }
    }
    return tables;
  }

  function extractMatches(tables, fallbackText) {
    const matches = [];
    const seen = new Set();
    const push = m => {
      if (!m) return;
      const key = m.date + "|" + m.home + "|" + m.score + "|" + m.away;
      if (seen.has(key)) return;
      seen.add(key);
      matches.push(m);
    };
    for (const t of tables) {
      for (const row of t.rows) {
        push(parseMatchRow(row));
        // Second pass: entire row as one blob
        if (Array.isArray(row) && row.length) push(parseMatchRow([Array.isArray(row)?row.join(" "):String(row)]));
      }
      // Third pass: table text lines
      if (t.text) for (const m of parseMatchesFromText(t.text)) push(m);
    }
    if (matches.length < 3 && fallbackText) {
      for (const m of parseMatchesFromText(fallbackText)) push(m);
    }
    return matches.slice(0, 60);
  }

  function computeAverages(matches, tables, text) {
    const averages = {};
    const push = (key, vals) => {
      const cleanVals = (vals || []).filter(v => Number.isFinite(Number(v))).map(Number);
      if (!cleanVals.length) return;
      const prev = averages[key]?.samplesList || [];
      const samplesList = prev.concat(cleanVals).slice(-60);
      const avg = samplesList.reduce((a, b) => a + b, 0) / samplesList.length;
      averages[key] = {
        avg: Number(avg.toFixed(3)),
        samples: samplesList.length,
        min: Math.min(...samplesList),
        max: Math.max(...samplesList),
        samplesList
      };
    };

    // From parsed H2H matches (goals)
    if (matches.length) {
      const hg = matches.map(m => m.homeGoals ?? m.homeScore).filter(v => Number.isFinite(Number(v))).map(Number).filter(n => n >= 0 && n <= 9);
      const ag = matches.map(m => m.awayGoals ?? m.awayScore).filter(v => Number.isFinite(Number(v))).map(Number).filter(n => n >= 0 && n <= 9);
      push("goalsHome", hg);
      push("goalsAway", ag);
      if (hg.length && ag.length && hg.length === ag.length) {
        push("goalsTotal", hg.map((h, i) => h + ag[i]));
        push("btts", hg.map((h, i) => (h > 0 && ag[i] > 0) ? 1 : 0));
        push("over25", hg.map((h, i) => (h + ag[i] >= 3) ? 1 : 0));
      }
    }

    // From generic metric tables inside H2H panels (incl. rows sem placar)
    for (const t of tables) {
      for (const row of t.rows) {
        const label = norm(row[0] || "");
        const rowBlob = norm(row.join(" "));
        const values = nums(row.slice(1).join(" "));
        if (!values.length) continue;
        if (/escante|corner|cantos/.test(label) || /escante|corner/.test(rowBlob)) push("corners", values);
        else if ((/gol|goal/.test(label) || /media de gols|avg goals|gols por jogo/.test(rowBlob)) && !/xg|expected/.test(label + rowBlob)) push("goals", values);
        else if (/chute|shot|finaliz/.test(label + rowBlob)) push("shots", values);
        else if (/posse|possession/.test(label + rowBlob)) push("possession", values);
        else if (/ataque|attack/.test(label + rowBlob) && !/perigoso|dangerous/.test(label + rowBlob)) push("attacks", values);
        else if (/perigoso|dangerous/.test(label + rowBlob)) push("dangerous", values);
        else if (/cart[aã]o|card|amarelo|yellow|vermelho|red/.test(label + rowBlob)) push("cards", values);
        else if (/xg|expected/.test(label + rowBlob)) push("xg", values);
        else if (/substit|subs/.test(label + rowBlob)) push("subs", values);
        else if (/impedimento|offside/.test(label + rowBlob)) push("offsides", values);
        else if (/falta|foul/.test(label + rowBlob)) push("fouls", values);
      }
    }

    // Texto livre: "Média de gols 1.4 1.2" / "Escanteios 5.1 4.8"
    const src = String(text || "");
    const metricLineRe = /(m[eé]dia\s+de\s+gols|avg\s*goals|gols?\s+por\s+jogo|escanteios?|corners?|chutes?|shots?|posse|possession|ataques?|attacks?|impedimentos?|offsides?|faltas?|fouls?|xg)\s*[:=\-]?\s*(-?\d+(?:[.,]\d+)?)\s+(-?\d+(?:[.,]\d+)?)/gi;
    let ml;
    while ((ml = metricLineRe.exec(src))) {
      const lab = norm(ml[1]);
      const vals = [Number(String(ml[2]).replace(",", ".")), Number(String(ml[3]).replace(",", "."))];
      if (/escante|corner/.test(lab)) push("corners", vals);
      else if (/gol|goal/.test(lab)) push("goals", vals);
      else if (/chute|shot/.test(lab)) push("shots", vals);
      else if (/posse|possession/.test(lab)) push("possession", vals);
      else if (/ataque|attack/.test(lab)) push("attacks", vals);
      else if (/impedimento|offside/.test(lab)) push("offsides", vals);
      else if (/falta|foul/.test(lab)) push("fouls", vals);
      else if (/xg/.test(lab)) push("xg", vals);
    }

    // Strip internal samplesList from output.
    const out = {};
    for (const [k, v] of Object.entries(averages)) {
      // 9.2.7: drop contaminated league-table averages
      if (/^goals/.test(k) && (v.avg > 4.5 || v.max > 7 || v.min < 0)) continue;
      if (k === "attacks" && v.avg > 200) continue;
      out[k] = { avg: v.avg, samples: v.samples, min: v.min, max: v.max };
    }
    return out;
  }

  function extract() {
    const root = findH2HRoot();
    const scope = root || document.querySelector("main,[role='main'],#content,.content") || document.body;
    const bodyText = clean(scope?.innerText || "").slice(0, 40000);
    const h2hTextMatch = bodyText.match(/(?:h2h|head\s*to\s*head|confrontos?|frente\s+a\s+frente|resultados?\s*\(\d+\))[\s\S]{0,20000}/i);
    const h2hText = h2hTextMatch ? h2hTextMatch[0] : (root ? bodyText.slice(0, 12000) : "");

    const tablesAll = extractTables(scope);
    // Prefer tables that look like the results grid from the screenshot.
    const relevant = tablesAll.filter(t => {
      const blob = norm(t.headers.join(" ") + " " + t.text.slice(0, 500));
      return /data|campeonato|casa|fora|placar|home|away|score|result/i.test(blob) ||
        t.rows.some(r => r.some(c => /\d{1,2}\s*[-–—−~xX]\s*\d{1,2}/.test(c)));
    });
    const tables = (relevant.length ? relevant : tablesAll).slice(0, 50);
    let matches = extractMatches(tables, h2hText || bodyText);

        // MAXIMIZE: free-text quando poucas partidas (SokkerPRO SPA / grids sem <table>)
    if (matches.length < 3) {
      const src = h2hText || bodyText;
      const seen = new Set(matches.map(m => `${m.home}|${m.score}|${m.away}`));
      const scoreLineRe = /([A-Za-zÀ-ú0-9 .'\/\-]{2,42}?)\s+(\d{1,2})\s*[-–—−xX×]\s*(\d{1,2})\s+([A-Za-zÀ-ú0-9 .'\/\-]{2,42})/g;
      let mm;
      while ((mm = scoreLineRe.exec(src)) && matches.length < 50) {
        let home = clean(mm[1]), away = clean(mm[4]);
        const hs = Number(mm[2]), as = Number(mm[3]);
        if (!home || !away || home.length > 40 || away.length > 40) continue;
        if (/data|campeonato|placar|vit[oó]ria|empate|resultado|m[eé]dia|avg|taxa/i.test(home + " " + away)) continue;
        const dm = home.match(/^(?:\d{1,2}\/\d{1,2}(?:\/\d{2,4})?\s+)?(.+)$/);
        if (dm) home = clean(dm[1]);
        home = home.replace(/^(?:S[eé]rie\s*[A-D]|Bundesliga|Regionalliga|Liga|Cup|Copa)\s+/i, "").trim();
        if (home.length < 2 || away.length < 2) continue;
        if (hs > 15 || as > 15) continue; // 9.2.7: ignore ranking/league noise as "scores"
        const key = `${home}|${hs}-${as}|${away}`;
        if (seen.has(key)) continue;
        seen.add(key);
        matches.push({ home, away, homeGoals: hs, awayGoals: as, score: `${hs}-${as}`, date: "", competition: "", source: "free-text" });
      }
      for (const line of src.split(/\n+/)) {
        const L = clean(line);
        if (L.length < 10 || L.length > 200 || !SCORE_RE.test(L)) continue;
        if (/vit[oó]rias|empates|resultados?\s*\(/i.test(L)) continue;
        const row = parseMatchRow(L.split(/\s*\|\s*|\t+/).map(clean).filter(Boolean)) || parseMatchRow([L]);
        if (!row) continue;
        const key = `${row.home}|${row.score}|${row.away}`;
        if (seen.has(key)) continue;
        seen.add(key);
        matches.push({ ...row, source: "free-text-line" });
        if (matches.length >= 50) break;
      }
    }

    let summary = parseSummary(scope);
    if (summary.homeWins == null && h2hText) {
      const s2 = parseSummary(h2hText);
      if (s2.homeWins != null) summary = s2;
    }
    const averages = computeAverages(matches, tables, h2hText || bodyText);

    // 9.2.7: always prefer match-row derivation when summary is missing OR absurd
    if (summary.homeWins != null && (summary.homeWins > 40 || summary.total > 80)) {
      summary.homeWins = summary.draws = summary.awayWins = summary.total = null;
    }
    if (summary.total == null && matches.length) summary.total = matches.length;
    if ((summary.homeWins == null || summary.draws == null || summary.awayWins == null) && matches.length) {
      let hw = 0, dr = 0, aw = 0, counted = 0;
      for (const m of matches) {
        const hg = Number(m.homeGoals ?? m.homeScore);
        const ag = Number(m.awayGoals ?? m.awayScore);
        if (!Number.isFinite(hg) || !Number.isFinite(ag)) continue;
        counted++;
        if (hg === ag) dr++;
        else if (hg > ag) hw++;
        else aw++;
      }
      if (counted > 0) {
        if (summary.homeWins == null) summary.homeWins = hw;
        if (summary.draws == null) summary.draws = dr;
        if (summary.awayWins == null) summary.awayWins = aw;
        if (summary.total == null) summary.total = counted;
      }
    }

    // Record-derived parameters for diagnostics / intelligence.
    const parameters = {
      matches: matches.length,
      homeWins: summary.homeWins,
      draws: summary.draws,
      awayWins: summary.awayWins,
      totalResults: summary.total,
      avgGoalsHome: averages.goalsHome?.avg ?? null,
      avgGoalsAway: averages.goalsAway?.avg ?? null,
      avgGoalsTotal: averages.goalsTotal?.avg ?? null,
      bttsRate: averages.btts?.avg ?? null,
      over25Rate: averages.over25?.avg ?? null,
      avgCorners: averages.corners?.avg ?? null
    };

    return {
      version: VERSION,
      fixtureId: fixtureId(),
      text: h2hText || bodyText.slice(0, 12000),
      tables,
      matches,
      summary,
      averages,
      parameters,
      rootFound: !!root,
      url: location.href,
      timestamp: Date.now()
    };
  }

  function isSafeInPageControl(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toLowerCase();
    const href = el.getAttribute?.("href") || el.href || "";
    // Never follow real navigations to other fixtures/pages.
    if (tag === "a" && href) {
      try {
        const u = new URL(href, location.href);
        if (u.origin !== location.origin) return false;
        if (u.pathname !== location.pathname) return false; // same fixture path only
      } catch { return false; }
    }
    // Prefer explicit tab/chip roles.
    const role = (el.getAttribute?.("role") || "").toLowerCase();
    if (role === "tab" || role === "button") return true;
    if (tag === "button" || tag === "summary") return true;
    // Anchors with hash-only or same-path are ok
    if (tag === "a" && (!href || href.startsWith("#") || href === location.href)) return true;
    return false;
  }

  async function openH2HTabs() {
    // Passive-first: if panel already visible, do NOT click anything.
    const already = extract();
    if (already.matches.length >= 3 || already.summary.total || (already.tables.length && already.rows)) {
      return 0;
    }
    const els = [...document.querySelectorAll("button,[role='tab'],[role='button'],summary")]
      .map(el => ({ el, s: score(el) }))
      .filter(x => x.s >= 8 && isSafeInPageControl(x.el))
      .sort((a, b) => b.s - a.s);
    let opened = 0;
    for (const x of els.slice(0, 3)) {
      try {
        x.el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
        opened++;
        await sleep(300);
        const probe = extract();
        if (probe.matches.length || probe.summary.total) break;
      } catch {}
    }
    return opened;
  }

  async function sweep(force = false) {
    if (!captureArmed && !force) return { ok: false, error: "H2H | não armado" };
    captureArmed = true;
    attemptedAt = Date.now();
    // Only attempt tab opens on explicit force (poll/diagnostic), never on passive observer.
    if (force) await openH2HTabs();
    let h;
    try { h = extract(); } catch (e) {
      try { console.warn(PREFIX, "extract:", e?.message || e); } catch {}
      return { ok: false, attempted: true, matches: 0, tables: 0, error: e?.message || String(e) };
    }
    const hasData = !!(h.matches.length || h.tables.length || h.text || h.summary.total || Object.keys(h.averages || {}).length);
    const hash = JSON.stringify({
      matches: h.matches.length,
      tables: h.tables.length,
      summary: h.summary,
      averages: h.averages,
      parameters: h.parameters
    });
    if (hasData && (hash !== lastHash || force)) {
      lastHash = hash;
      lastSent = Date.now();
      await send("H2H_CAPTURE", h);
    }
    return {
      ok: hasData,
      attempted: true,
      matches: h.matches.length,
      tables: h.tables.length,
      summary: h.summary,
      parameters: h.parameters,
      rootFound: h.rootFound,
      error: hasData ? null : "H2H | painel sem dados"
    };
  }

  function schedule(force = false, delay = 120) {
    clearTimeout(scheduled);
    scheduled = setTimeout(() => sweep(force).catch(() => {}), delay);
  }

  const observer = new MutationObserver(() => schedule(false, 220));
  let discoveryObserver = null;
  let rootRebindTimer = null;

  function bindObserver() {
    const root = findH2HRoot();
    if (!root) return false;
    try { observer.disconnect(); } catch {}
    try {
      observer.observe(root, { childList: true, subtree: true, characterData: false, attributes: false });
      return true;
    } catch { return false; }
  }

  function start() {
    if (!bindObserver()) {
      try {
        discoveryObserver = new MutationObserver(() => {
          if (bindObserver()) { try { discoveryObserver.disconnect(); } catch {} }
        });
        discoveryObserver.observe(document.body || document.documentElement || document, { childList: true, subtree: true });
      } catch {}
    }
    rootRebindTimer = setInterval(() => { bindObserver(); }, 5000);
    schedule(false, 400);
    setInterval(() => {
      try {
        const h = extract();
        if (h && (h.matches.length || h.tables.length)) schedule(false, 80);
      } catch (e) {
        try { console.warn(PREFIX, "extract interval:", e?.message || e); } catch {}
      }
    }, 1500);
    window.addEventListener("popstate", () => schedule(false, 200));
    for (const m of ["pushState", "replaceState"]) {
      const o = history[m];
      history[m] = function (...a) {
        const r = o.apply(this, a);
        schedule(false, 200);
        return r;
      };
    }
    document.addEventListener("click", e => {
      const el = e.target?.closest?.("a,button,[role='tab'],[role='button'],summary");
      if (el && score(el) > 0) schedule(false, 300);
    }, true);
  }

  chrome.runtime.onMessage.addListener((m, s, r) => {
    if (m?.type === "ARM_CAPTURE") {
      // Não responder: content.js é o dono oficial da resposta de ARM_CAPTURE
      // (preflight + fixtureId completos). Responder aqui fechava o canal
      // antes do content.js terminar (CS_REJECTION).
      captureArmed = true;
      try { start(); } catch {}
      return false;
    }
    if (m?.type === "H2H_CAPTURE" || m?.type === "H2H_SWEEP" || m?.type === "H2H_POLL") {
      if (!captureArmed) {
        captureArmed = true;
        try { start(); } catch {}
      }
      sweep(true).then(res => r(res || { ok: false })).catch(e => r({ ok: false, error: e?.message || String(e) }));
      return true;
    }
  });

  window.addEventListener("cornerai-h2h-poll", () => {
    captureArmed = true;
    try { start(); } catch {}
    sweep(true).catch(() => {});
  });
  console.debug(PREFIX, "v" + VERSION, location.href);
})();
