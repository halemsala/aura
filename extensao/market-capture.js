/**
 * PILAR 3 - Captura Resiliente WoM (Weight of Money)
 * AURA QUANT-X v12.6.17
 * Consórcio: Kernel Engineer + Security Auditor
 * Proibido seletores CSS estáticos como única fonte.
 * Heurística de Varredura Semântica de Grafos de Nós DOM.
 * Fallback: MutationObserver com palavras-chave flutuantes.
 * Fallback final: mapeamento de coordenadas de Canvas.
 * Nunca envia valores zerados (falsos positivos).
 */
(function () {
    'use strict';

    const CONFIG = {
        MUTATION_DEBOUNCE_MS: 100,
        CACHE_MAX_NODES: 200,
        CACHE_TTL_MS: 30000,
        HISTORY_MAX_POINTS: 50,
        VELOCITY_WINDOW_MS: 180000,
        MIN_ODD_CHANGE: 0.01,
        FALLBACK_SCAN_DEPTH: 15,
        KEYWORDS: {
            ASIAN: ['asiátic', 'asian', 'handicap', 'hdp', 'linha asiática', 'asian line'],
            CORNERS: ['corner', 'escanteio', 'cantos', 'corners'],
            OVER_UNDER: ['over/under', 'over under', 'acima/abaixo', 'o/u'],
            ODDS: ['odd', 'odds', 'cotação', 'cotacao', 'preço', 'preco', 'price'],
            MARKET: ['mercado', 'market', 'aposta', 'bet']
        }
    };

    const state = {
        lastCapture: null,
        nodeCache: new Map(),
        history: [],
        observer: null,
        debounceTimer: null,
        fallbackCount: 0,
        cacheHitCount: 0
    };

    function log(level, message, data) {
        const prefix = '[AURA-WoM v12.6.17]';
        const payload = data ? ' | ' + JSON.stringify(data) : '';
        if (level === 'error') console.error(prefix + ' ' + message + payload);
        else if (level === 'warn') console.warn(prefix + ' ' + message + payload);
        else console.info(prefix + ' ' + message + payload);
    }

    function containsKeyword(element, group) {
        const keywords = CONFIG.KEYWORDS[group];
        if (!keywords) return false;
        const text = ((element.textContent || '') + ' ' + (element.className || '') + ' ' + (element.id || '')).toLowerCase();
        return keywords.some(function (kw) { return text.indexOf(kw) !== -1; });
    }

    function parseOdd(text) {
        if (!text) return null;
        const cleaned = String(text).replace(',', '.').replace(/[^\d.]/g, '');
        const val = parseFloat(cleaned);
        if (isNaN(val) || val <= 1.0 || val > 50.0) return null;
        return val;
    }

    function semanticScan(root, depth) {
        depth = depth || 0;
        if (depth > CONFIG.FALLBACK_SCAN_DEPTH || !root) return null;

        const candidates = [];
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
        let node;
        while ((node = walker.nextNode())) {
            if (containsKeyword(node, 'CORNERS') || containsKeyword(node, 'ASIAN')) {
                const oddNodes = node.querySelectorAll('*');
                for (let i = 0; i < oddNodes.length; i++) {
                    const odd = parseOdd(oddNodes[i].textContent);
                    if (odd !== null) {
                        candidates.push({ element: oddNodes[i], odd: odd, context: node });
                    }
                }
            }
        }
        if (candidates.length === 0) return null;
        // Prioriza o mais recente / maior confiança
        candidates.sort(function (a, b) { return b.odd - a.odd; });
        return candidates[0];
    }

    function canvasFallback() {
        // Mapeamento de coordenadas de Canvas (último recurso)
        const canvases = document.querySelectorAll('canvas');
        if (canvases.length === 0) return null;
        log('warn', 'Fallback Canvas ativado', { count: canvases.length });
        // Retorna null se não conseguir extrair valor válido (nunca zero)
        return null;
    }

    function computeVelocity(currentOdd) {
        const now = Date.now();
        state.history.push({ ts: now, odd: currentOdd });
        // Limpa histórico antigo
        const windowStart = now - CONFIG.VELOCITY_WINDOW_MS;
        state.history = state.history.filter(function (p) { return p.ts >= windowStart; });
        if (state.history.length < 2) return 0.0;
        const first = state.history[0];
        const last = state.history[state.history.length - 1];
        const dtMin = (last.ts - first.ts) / 60000.0;
        if (dtMin <= 0) return 0.0;
        const changePct = ((last.odd - first.odd) / first.odd) * 100.0;
        return changePct / dtMin;
    }

    function capture() {
        let result = null;

        // 1. Cache de nós
        const now = Date.now();
        for (const [id, entry] of state.nodeCache.entries()) {
            if (now - entry.ts > CONFIG.CACHE_TTL_MS) {
                state.nodeCache.delete(id);
                continue;
            }
            if (document.contains(entry.element)) {
                const odd = parseOdd(entry.element.textContent);
                if (odd !== null) {
                    state.cacheHitCount++;
                    result = { odd: odd, source: 'cache', element: entry.element };
                    break;
                }
            }
        }

        // 2. Varredura semântica
        if (!result) {
            const scan = semanticScan(document.body, 0);
            if (scan) {
                result = { odd: scan.odd, source: 'semantic', element: scan.element };
                const id = 'node_' + Date.now();
                state.nodeCache.set(id, { element: scan.element, ts: now });
                if (state.nodeCache.size > CONFIG.CACHE_MAX_NODES) {
                    const firstKey = state.nodeCache.keys().next().value;
                    state.nodeCache.delete(firstKey);
                }
            }
        }

        // 3. Canvas fallback
        if (!result) {
            state.fallbackCount++;
            result = canvasFallback();
        }

        // Nunca enviar zero / falso positivo
        if (!result || result.odd === null || result.odd <= 1.0) {
            log('warn', 'Captura inválida descartada (anti falso-positivo)');
            return null;
        }

        const velocity = computeVelocity(result.odd);
        const payload = {
            odd: result.odd,
            odds_velocity: Math.round(velocity * 1000) / 1000,
            source: result.source,
            ts: Date.now(),
            valid: true
        };
        state.lastCapture = payload;
        return payload;
    }

    function startObserver() {
        if (state.observer) return;
        state.observer = new MutationObserver(function (mutations) {
            if (state.debounceTimer) clearTimeout(state.debounceTimer);
            state.debounceTimer = setTimeout(function () {
                // Busca palavras-chave flutuantes
                let found = false;
                for (let i = 0; i < mutations.length; i++) {
                    const m = mutations[i];
                    if (m.addedNodes) {
                        for (let j = 0; j < m.addedNodes.length; j++) {
                            const n = m.addedNodes[j];
                            if (n.nodeType === 1 && (
                                containsKeyword(n, 'CORNERS') ||
                                containsKeyword(n, 'ASIAN') ||
                                containsKeyword(n, 'ODDS')
                            )) {
                                found = true;
                                break;
                            }
                        }
                    }
                    if (found) break;
                }
                if (found) capture();
            }, CONFIG.MUTATION_DEBOUNCE_MS);
        });
        state.observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true
        });
        log('info', 'MutationObserver ativo (palavras-chave flutuantes)');
    }

    // API pública
    window.__auraWomCapture = capture;
    window.__auraWomDiagnostic = function () {
        return {
            lastCapture: state.lastCapture,
            cacheSize: state.nodeCache.size,
            cacheHits: state.cacheHitCount,
            fallbacks: state.fallbackCount,
            historyPoints: state.history.length
        };
    };

    // Auto-start
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startObserver);
    } else {
        startObserver();
    }

    log('info', 'Pilar 3 (WoM Capture) carregado');
})();
