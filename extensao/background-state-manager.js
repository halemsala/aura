/*
 * PILAR 6 - Background State Manager
 * AURA QUANT-X v12.7.0-RECONSOLIDADO
 *
 * Compatibilidade MV3: o service worker oficial (`background.js`) é o único
 * dono do estado, outbox, persistência e retry. Este módulo não cria um segundo
 * singleton. Ele expõe a API do Pilar 6 e delega para a fachada instalada pelo
 * worker depois que o estado canônico estiver inicializado.
 */
(function (global) {
    'use strict';

    function active() {
        return global.__AURA_ACTIVE_STATE_ADAPTER || null;
    }

    const api = {
        getFullStats: function () {
            const impl = active();
            return impl && typeof impl.getFullStats === 'function' ? impl.getFullStats() : { active: false, reason: 'worker_not_ready' };
        },
        getWomState: function () {
            const impl = active();
            return impl && typeof impl.getWomState === 'function' ? impl.getWomState() : { stale: true, source: 'none' };
        },
        getRecentTelemetry: function (count) {
            const impl = active();
            return impl && typeof impl.getRecentTelemetry === 'function' ? impl.getRecentTelemetry(count) : [];
        },
        getServices: function () {
            const impl = active();
            return impl && typeof impl.getServices === 'function' ? impl.getServices() : {};
        },
        healthCheck: async function () {
            const services = api.getServices();
            return Object.values(services).every(function (service) { return service && service.healthy !== false; });
        },
        getTelemetry: function (count) {
            return api.getRecentTelemetry(count);
        },
        getErrors: function () {
            const stats = api.getFullStats();
            return Array.isArray(stats.errors) ? stats.errors : (Array.isArray(stats.diagnostics?.errors) ? stats.diagnostics.errors : []);
        },
        getBackoffStats: function () {
            const stats = api.getFullStats();
            return stats.webhook || {};
        },
        uptimeMs: function () {
            const stats = api.getFullStats();
            return stats.startedAt ? Date.now() - Number(stats.startedAt) : 0;
        },
        sendTelemetry: function (payload) {
            const impl = active();
            if (impl && typeof impl.sendTelemetry === 'function') return impl.sendTelemetry(payload);
            return Promise.resolve({ ok: false, error: 'worker_not_ready' });
        },
        performCleanup: function () {
            const impl = active();
            return impl && typeof impl.performCleanup === 'function' ? impl.performCleanup() : { active: false };
        },
        get CONFIG() {
            return {
                canonical: true,
                source: 'background.js',
                telemetryBuffer: 'active_state',
                retry: 'active_outbox'
            };
        }
    };

    global.AURA_STATE_MANAGER = api;
    global.__auraState = api;
})(typeof self !== 'undefined' ? self : globalThis);
