/**
 * AURA QUANT-X - captura SokkerPRO WebView2
 * Build: V28-SOKKERPRO-DOM-HARDENED
 * Baseado no DOM real (fixture SokkerPRO PT-BR):
 *  - stat-row: home | label | away  (Escanteios, Ataques, xG, APPM, Posse...)
 *  - gauge-title + gauge-num (pares)
 *  - shot-label + shot-num-left/right
 *  - pressao_vertical
 *  - corner-icon home-corner / away-corner
 *  - title: "TimeA 0 x 0 TimeB"
 */
(function () {
    'use strict';
    var ALLOWED_HOSTS = new Set([
        'sokkerpro.com', 'www.sokkerpro.com',
        'm2.sokkerpro.com', 'm3.sokkerpro.com', 'm4.sokkerpro.com', 'app.sokkerpro.com'
    ]);
    var host = String(window.location.hostname || '').toLowerCase().replace(/\.$/, '');
    if (!ALLOWED_HOSTS.has(host)) return;
    if (window.__AURA_CAPTURE_V28_DOM__) return;
    window.__AURA_CAPTURE_V28_DOM__ = true;
    window.__AURA_CAPTURE_V28_SOKKERPRO_RICH__ = true;

    function isSokkerUrl(url) {
        try {
            var u = new URL(String(url || ''), location.href);
            return ALLOWED_HOSTS.has(u.hostname.toLowerCase().replace(/\.$/, ''));
        } catch (e) { return false; }
    }
    function stayInside(url) {
        if (!url) return false;
        try {
            var abs = new URL(String(url), location.href).href;
            if (!isSokkerUrl(abs)) return false;
            if (abs === location.href) return true;
            location.href = abs;
            return true;
        } catch (e) { return false; }
    }
    var rawOpen = window.open;
    window.open = function (url) {
        if (stayInside(url)) return window;
        if (typeof rawOpen === 'function') return rawOpen.apply(this, arguments);
        return null;
    };
    document.addEventListener('click', function (ev) {
        var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
        if (!a) return;
        var href = a.getAttribute('href') || '';
        if (!/fixture|partida|match/i.test(href) && a.target !== '_blank') return;
        if (!isSokkerUrl(a.href)) return;
        ev.preventDefault();
        ev.stopPropagation();
        stayInside(a.href);
    }, true);

    var INTERVAL_MS = 1000;
    var FORCE_MS = 5000;
    var capturing = false;
    var timer = null;
    var lastFp = '';
    var lastSendAt = 0;
    var lastValidTimestamp = Date.now();
    var canarySignaled = false;
    var CANARY_MAX_SILENCE_MS = 8000;
    var STALE_WARN_MS = 12000;
    var HEARTBEAT_EVERY = 15; // sends
    var sendCount = 0;

    function textOf(root) {
        return String((root && (root.innerText || root.textContent)) || '')
            .replace(/\u00a0/g, ' ')
            .replace(/[ \t]+/g, ' ')
            .replace(/\n{2,}/g, '\n')
            .trim();
    }
    function toInt(v) {
        if (v == null || v === '' || v === '-' || v === '?') return null;
        var n = parseInt(String(v).replace(/[^\d-]/g, ''), 10);
        return Number.isFinite(n) ? n : null;
    }
    function toNum(v) {
        if (v == null || v === '' || v === '-' || v === '?') return null;
        var n = parseFloat(String(v).replace('%', '').replace(',', '.').replace(/[^\d.-]/g, ''));
        return Number.isFinite(n) ? n : null;
    }
    function cleanTeam(s) {
        if (!s) return null;
        s = String(s).replace(/\s+/g, ' ').trim();
        s = s.replace(/\s*[·|].*$/, '').trim();
        if (s.length < 2 || s.length > 48) return null;
        if (/^(AO VIVO|LIVE|Press|Ataques|xG|Chutes|Escanteio|Odds|FT|HT)/i.test(s)) return null;
        return s;
    }
    function fixtureIdFromLocation() {
        var m = String(location.pathname || '').match(/\/(?:fixture|partida|match)\/(\d+)/i);
        if (m) return m[1];
        m = String(location.href || '').match(/[?&](?:id|fixtureId|fixture)=(\d+)/i);
        return m ? m[1] : null;
    }

    /** Mapa label -> {home, away} a partir de .stat-row + fallbacks (V28 hardened) */
    function parseStatRows() {
        var map = {};
        // Primary: classic .stat-row
        var rows = document.querySelectorAll('.stat-row, [class*="stat-row"], .stats-row, .match-stat');
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var labelEl = row.querySelector('.stat-label, [class*="stat-label"], .label, .stat-name');
            if (!labelEl) {
                // try first text child as label
                var kids = row.children;
                if (kids && kids.length >= 3) labelEl = kids[1];
            }
            if (!labelEl) continue;
            var label = textOf(labelEl).replace(/\s+/g, ' ').trim();
            if (!label || label.length > 40) continue;
            var vals = row.querySelectorAll('.stat-value, [class*="stat-value"], .value, .stat-home, .stat-away');
            var home = null, away = null;
            if (vals.length >= 2) {
                home = textOf(vals[0]);
                away = textOf(vals[vals.length - 1]);
            } else {
                var nums = textOf(row).match(/(\d+[.,]?\d*%?|\?|-)/g);
                if (nums && nums.length >= 2) {
                    home = nums[0]; away = nums[nums.length - 1];
                }
            }
            var key = label.toLowerCase();
            map[key] = { home: home, away: away, label: label };
        }
        // Extra fallback: any element with data-stat or aria labels containing known keys
        if (Object.keys(map).length < 4) {
            var all = document.querySelectorAll('[data-stat], [class*="corner"], [class*="ataque"], [class*="posse"]');
            for (var j = 0; j < all.length; j++) {
                var el = all[j];
                var t = textOf(el);
                if (/escanteio|corner|ataque|posse|xg/i.test(t) && /\d/.test(t)) {
                    var nums2 = t.match(/(\d+[.,]?\d*%?)/g);
                    if (nums2 && nums2.length >= 2) {
                        var lk = (t.match(/escanteio|corner|ataque|posse|xg/i) || ['extra'])[0].toLowerCase();
                        if (!map[lk]) map[lk] = { home: nums2[0], away: nums2[nums2.length-1], label: lk };
                    }
                }
            }
        }
        return map;
    }

    function pairFromMap(map, labels, kind) {
        for (var i = 0; i < labels.length; i++) {
            var k = labels[i].toLowerCase();
            // exact or contains
            if (map[k]) {
                var h = kind === 'float' ? toNum(map[k].home) : toInt(map[k].home);
                var a = kind === 'float' ? toNum(map[k].away) : toInt(map[k].away);
                // percent strings
                if (kind === 'float' && h == null) h = toNum(map[k].home);
                if (kind === 'float' && a == null) a = toNum(map[k].away);
                if (h != null || a != null) return { home: h, away: a };
            }
            for (var key in map) {
                if (key.indexOf(k) !== -1) {
                    var hh = kind === 'float' ? toNum(map[key].home) : toInt(map[key].home);
                    var aa = kind === 'float' ? toNum(map[key].away) : toInt(map[key].away);
                    if (hh != null || aa != null) return { home: hh, away: aa };
                }
            }
        }
        return { home: null, away: null };
    }

    function parseGauges() {
        var out = {};
        var cols = document.querySelectorAll('.gauge-col');
        for (var i = 0; i < cols.length; i++) {
            var titleEl = cols[i].querySelector('.gauge-title');
            if (!titleEl) continue;
            var title = textOf(titleEl);
            var nums = cols[i].querySelectorAll('.gauge-num');
            if (nums.length >= 2) {
                out[title.toLowerCase()] = {
                    home: textOf(nums[0]),
                    away: textOf(nums[1])
                };
            } else if (nums.length === 1) {
                // single gauge sometimes shows dominant side only — skip asymmetric
            }
        }
        return out;
    }

    function parseShots() {
        var out = {};
        var labels = document.querySelectorAll('.shot-label');
        for (var i = 0; i < labels.length; i++) {
            var lab = textOf(labels[i]);
            var parent = labels[i].closest('.shot-block') || labels[i].parentElement;
            if (!parent) continue;
            var left = parent.querySelector('.shot-num-left');
            var right = parent.querySelector('.shot-num-right');
            // also try siblings
            var root = labels[i].closest('div') || parent;
            if (!left) left = root.querySelector('.shot-num-left');
            if (!right) right = root.querySelector('.shot-num-right');
            // walk up a bit
            var p = labels[i].parentElement;
            for (var up = 0; up < 4 && p && (!left || !right); up++, p = p.parentElement) {
                if (!left) left = p.querySelector('.shot-num-left');
                if (!right) right = p.querySelector('.shot-num-right');
            }
            out[lab.toLowerCase()] = {
                home: left ? textOf(left) : null,
                away: right ? textOf(right) : null
            };
        }
        return out;
    }

    function parsePressure() {
        var el = document.querySelector('.pressao_vertical');
        if (el) {
            var t = textOf(el);
            var m = t.match(/(\d{1,3})\s*%/);
            if (m) return toInt(m[1]);
        }
        var body = textOf(document.body).slice(0, 8000);
        var pm = body.match(/Press[aã]o\s+(\d{1,3})\s*%/i);
        return pm ? toInt(pm[1]) : null;
    }

    function parseCornerIcons() {
        var home = document.querySelectorAll('.home-corner, .corner-icon.home-corner').length;
        var away = document.querySelectorAll('.away-corner, .corner-icon.away-corner').length;
        // de-dup if both selectors match same nodes
        if (!home && !away) {
            home = document.querySelectorAll('[class*="home-corner"]').length;
            away = document.querySelectorAll('[class*="away-corner"]').length;
        }
        return { home: home || null, away: away || null };
    }

    function parseClock() {
        var minute = null, extra = 0, status = null;
        var candidates = document.querySelectorAll(
            '.game-status--live, .game-status, .minute-status, [class*="live-minute"], [class*="match-minute"]'
        );
        for (var i = 0; i < candidates.length; i++) {
            var t = textOf(candidates[i]);
            if (!t || t.length > 24) continue;
            if (/FT|Encerrado|Final/i.test(t)) { status = 'FT'; continue; }
            if (/HT|Intervalo/i.test(t)) { status = 'HT'; continue; }
            var m = t.match(/(\d{1,3})\s*\+\s*(\d{1,2})/);
            if (m) { minute = toInt(m[1]); extra = toInt(m[2]) || 0; status = status || 'live'; break; }
            m = t.match(/^(\d{1,3})['′]?$/);
            if (m) { minute = toInt(m[1]); status = status || 'live'; break; }
            m = t.match(/(?:AO\s*VIVO|LIVE)\s+(\d{1,3})/i);
            if (m) { minute = toInt(m[1]); status = status || 'live'; break; }
        }
        if (minute == null) {
            var body = textOf(document.body).slice(0, 4000);
            var lm = body.match(/(?:AO\s*VIVO|LIVE)\s+(\d{1,3})(?:\s*\+\s*(\d{1,2}))?/i);
            if (lm) { minute = toInt(lm[1]); extra = toInt(lm[2]) || 0; status = 'live'; }
        }
        return { minute: minute, extra: extra, status: status };
    }

    function parseTeamsScore() {
        var home = null, away = null, scoreHome = null, scoreAway = null;
        var title = String(document.title || '');
        var titleMatch = title.match(/^(.+?)\s+(\d+)\s*[x:\-]\s*(\d+)\s+(.+?)(?:\s+[-\u2013|]|$)/i);
        if (titleMatch) {
            home = cleanTeam(titleMatch[1]);
            scoreHome = toInt(titleMatch[2]);
            scoreAway = toInt(titleMatch[3]);
            away = cleanTeam(titleMatch[4]);
        }
        // fx-score nodes
        var scores = document.querySelectorAll('.fx-score, .cd-score, .col-score');
        if (scores.length >= 2 && scoreHome == null) {
            scoreHome = toInt(textOf(scores[0]));
            scoreAway = toInt(textOf(scores[1]));
        }
        return { home: home, away: away, scoreHome: scoreHome, scoreAway: scoreAway };
    }

    function extractView() {
        var fid = fixtureIdFromLocation();
        var teams = parseTeamsScore();
        var clock = parseClock();
        var map = parseStatRows();
        var gauges = parseGauges();
        var shots = parseShots();
        var pressurePct = parsePressure();
        var cornerIcons = parseCornerIcons();

        function preferPair(domPair, gaugeKey, kind) {
            if (domPair && (domPair.home != null || domPair.away != null)) return domPair;
            if (gaugeKey && gauges[gaugeKey.toLowerCase()]) {
                var g = gauges[gaugeKey.toLowerCase()];
                return {
                    home: kind === 'float' ? toNum(g.home) : toInt(g.home),
                    away: kind === 'float' ? toNum(g.away) : toInt(g.away)
                };
            }
            return { home: null, away: null };
        }

        var attacks = preferPair(pairFromMap(map, ['ataques'], 'int'), 'ataques', 'int');
        // avoid matching "ataques perigosos" for plain ataques — pairFromMap contains may overmatch
        if (map['ataques']) {
            attacks = {
                home: toInt(map['ataques'].home),
                away: toInt(map['ataques'].away)
            };
        }
        var dangerous = { home: null, away: null };
        if (map['ataques perigosos']) {
            dangerous = { home: toInt(map['ataques perigosos'].home), away: toInt(map['ataques perigosos'].away) };
        } else {
            dangerous = preferPair(pairFromMap(map, ['ataques perigosos', 'dangerous attacks'], 'int'), 'ataques perigosos', 'int');
        }

        var xg = { home: null, away: null };
        if (map['xg']) xg = { home: toNum(map['xg'].home), away: toNum(map['xg'].away) };
        else xg = preferPair(null, 'xg', 'float');

        var shotsOn = { home: null, away: null };
        if (map['chutes a gol'] || map['chutes no gol']) {
            var sk = map['chutes a gol'] || map['chutes no gol'];
            shotsOn = { home: toInt(sk.home), away: toInt(sk.away) };
        } else if (shots['chutes no gol']) {
            shotsOn = { home: toInt(shots['chutes no gol'].home), away: toInt(shots['chutes no gol'].away) };
        }

        var shotsOff = { home: null, away: null };
        if (map['chutes ao lado']) {
            shotsOff = { home: toInt(map['chutes ao lado'].home), away: toInt(map['chutes ao lado'].away) };
        } else if (shots['chutes ao lado']) {
            shotsOff = { home: toInt(shots['chutes ao lado'].home), away: toInt(shots['chutes ao lado'].away) };
        }

        var totalShots = pairFromMap(map, ['total de chutes'], 'int');
        var poss = pairFromMap(map, ['posse de bola', 'posse'], 'int');
        var fouls = pairFromMap(map, ['faltas'], 'int');
        var yellow = pairFromMap(map, ['cartões amarelos', 'amarelos', 'cartoes amarelos'], 'int');
        var red = pairFromMap(map, ['cartões vermelhos', 'vermelhos', 'cartoes vermelhos'], 'int');
        var cards = pairFromMap(map, ['cartões', 'cartoes'], 'float'); // averages in H2H sometimes

        // Escanteios — DOM stat-row first, then icons
        var cornersHome = null, cornersAway = null;
        if (map['escanteios']) {
            cornersHome = toInt(map['escanteios'].home);
            cornersAway = toInt(map['escanteios'].away);
        }
        if (cornersHome == null && cornerIcons.home != null) {
            cornersHome = cornerIcons.home;
            cornersAway = cornerIcons.away;
        }

        // APPM windows (SokkerPRO uses APPM not APM)
        var appm1 = pairFromMap(map, ['appm 1 min', 'appm 1m'], 'float');
        var appm3 = pairFromMap(map, ['appm 3 min', 'appm 3m'], 'float');
        var appm5 = pairFromMap(map, ['appm 5 min', 'appm 5m'], 'float');
        var appm10 = pairFromMap(map, ['appm 10 min', 'appm 10m'], 'float');
        // primary APM = APPM 10 min or APPM Total
        var apmHome = appm10.home != null ? appm10.home : appm5.home;
        var apmAway = appm10.away != null ? appm10.away : appm5.away;
        if (apmHome == null && map['appm total']) {
            apmHome = toNum(map['appm total'].home);
            apmAway = toNum(map['appm total'].away);
        }
        // fallback rate
        if (apmHome == null && clock.minute && clock.minute > 0 && dangerous.home != null) {
            apmHome = Math.round((dangerous.home / clock.minute) * 100) / 100;
            apmAway = dangerous.away != null ? Math.round((dangerous.away / clock.minute) * 100) / 100 : null;
        }

        var saves = pairFromMap(map, ['defesas do goleiro', 'defesas'], 'int');
        var offsides = pairFromMap(map, ['impedimentos', 'impedimento'], 'int');

        // Timeline corner events (text only, team unknown often)
        var events = [];
        var bodyShort = textOf(document.body).slice(0, 15000);
        var evRe = /(\d{1,2})[ºo°]?\s*Escanteio/gi;
        var em;
        while ((em = evRe.exec(bodyShort))) {
            events.push({ type: 'corner', label: em[0], team: null });
        }

        var paramHits = 0;
        function hit(p) { if (p && (p.home != null || p.away != null)) paramHits++; }
        if (teams.home) paramHits++;
        if (teams.away) paramHits++;
        if (clock.minute != null) paramHits++;
        if (cornersHome != null) paramHits++;
        hit(attacks); hit(dangerous); hit(xg); hit(shotsOn); hit(poss);

        var quality = 0.2;
        if (teams.home && teams.away) quality += 0.15;
        if (clock.minute != null) quality += 0.1;
        if (cornersHome != null) quality += 0.1;
        if (xg.home != null) quality += 0.1;
        if (dangerous.home != null) quality += 0.1;
        if (paramHits >= 6) quality += 0.15;
        quality = Math.min(1, quality);

        return {
            schema: 'cornerai-analyst-2',
            capture_build: 'V28-SOKKERPRO-DOM-HARDENED',
            fixture_id: fid,
            home: teams.home,
            away: teams.away,
            score_home: teams.scoreHome,
            score_away: teams.scoreAway,
            minute: clock.minute,
            extra: clock.extra,
            status: clock.status || (fid ? 'live' : null),
            pressure_gauge: pressurePct,
            attacks_home: attacks.home,
            attacks_away: attacks.away,
            dangerous_home: dangerous.home,
            dangerous_away: dangerous.away,
            xg_home: xg.home,
            xg_away: xg.away,
            shots_on_home: shotsOn.home,
            shots_on_away: shotsOn.away,
            shots_off_home: shotsOff.home,
            shots_off_away: shotsOff.away,
            total_shots_home: totalShots.home,
            total_shots_away: totalShots.away,
            possession_home: poss.home,
            possession_away: poss.away,
            corners_home: cornersHome,
            corners_away: cornersAway,
            apm_home: apmHome,
            apm_away: apmAway,
            appm_1_home: appm1.home,
            appm_1_away: appm1.away,
            appm_3_home: appm3.home,
            appm_3_away: appm3.away,
            appm_5_home: appm5.home,
            appm_5_away: appm5.away,
            appm_10_home: appm10.home,
            appm_10_away: appm10.away,
            fouls_home: fouls.home,
            fouls_away: fouls.away,
            yellow_home: yellow.home,
            yellow_away: yellow.away,
            red_home: red.home,
            red_away: red.away,
            saves_home: saves.home,
            saves_away: saves.away,
            offsides_home: offsides.home,
            offsides_away: offsides.away,
            param_hits: paramHits,
            quality: Math.round(quality * 100) / 100,
            corner_events: events,
            fixture: {
                id: fid,
                home: teams.home,
                away: teams.away,
                minute: clock.minute,
                extra: clock.extra,
                status: clock.status || (fid ? 'live' : null),
                score: { home: teams.scoreHome, away: teams.scoreAway }
            },
            pressure: {
                gauge: pressurePct,
                attacks: attacks,
                dangerous: dangerous,
                apm: { home: apmHome, away: apmAway },
                xg: xg,
                shotsOn: shotsOn,
                shotsOff: shotsOff
            },
            corners: {
                total: { home: cornersHome, away: cornersAway },
                events: events
            },
            stats: {
                attacks: attacks,
                dangerous: dangerous,
                xg: xg,
                shotsOn: shotsOn,
                shotsOff: shotsOff,
                totalShots: totalShots,
                possession: poss,
                fouls: fouls,
                appm: { m1: appm1, m3: appm3, m5: appm5, m10: appm10 }
            },
            source: 'sokkerpro-dom',
            url: String(location.href || ''),
            ts: Date.now()
        };
    }

    function fingerprint(view) {
        var f = view.fixture || {};
        return [
            f.id || '', f.minute, f.extra,
            view.corners_home, view.corners_away,
            view.dangerous_home, view.dangerous_away,
            view.xg_home, view.xg_away,
            view.apm_home, view.apm_away,
            view.score_home, view.score_away,
            view.param_hits
        ].join('|');
    }

    function send(view, force) {
        try {
            var fp = fingerprint(view);
            var now = Date.now();
            if (!force && fp === lastFp && (now - lastSendAt) < FORCE_MS) return false;
            if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
                window.chrome.webview.postMessage({
                    type: 'AURA_SOKKERPRO_CAPTURE',
                    payload: view,
                    meta: { build: 'V27-SOKKERPRO-DOM', force: !!force }
                });
                lastFp = fp;
                lastSendAt = now;
                return true;
            }
        } catch (err) { /* silent */ }
        return false;
    }

    function emitCanaryError(detail) {
        try {
            if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
                window.chrome.webview.postMessage({
                    type: 'CAPTURE_ERROR',
                    detail: detail,
                    url: window.location.href,
                    capture_build: 'V28-SOKKERPRO-DOM-HARDENED'
                });
            }
        } catch (e) { }
    }

    function cycle() {
        try {
            var view = extractView();
            if (view && (view.fixture_id || view.home || view.fixture && view.fixture.id)) {
                lastValidTimestamp = Date.now();
                canarySignaled = false;
                var force = (Date.now() - lastSendAt) >= FORCE_MS;
                send(view, force);
                return;
            }
            if (!canarySignaled && Date.now() - lastValidTimestamp > CANARY_MAX_SILENCE_MS) {
                canarySignaled = true;
                emitCanaryError('DOM_BROKEN_OR_PAGE_UNLOADED');
            }
        } catch (e) {
            if (!canarySignaled && Date.now() - lastValidTimestamp > CANARY_MAX_SILENCE_MS) {
                canarySignaled = true;
                emitCanaryError('CAPTURE_EXCEPTION');
            }
        }
    }

    window.AuraCapture = {
        start: function () {
            if (capturing) return;
            capturing = true;
            cycle();
            timer = setInterval(cycle, INTERVAL_MS);
        },
        stop: function () {
            capturing = false;
            if (timer) { clearInterval(timer); timer = null; }
        },
        captureOnce: cycle,
        debugExtract: extractView,
        version: 'V27-SOKKERPRO-DOM'
    };

    if (document.readyState !== 'loading') setTimeout(window.AuraCapture.start, 400);
    else document.addEventListener('DOMContentLoaded', function () {
        setTimeout(window.AuraCapture.start, 400);
    });
})();
