/**
 * PILAR 7 - Interface Sidepanel Dinâmica
 * AURA QUANT-X v12.7.0-RECONSOLIDADO
 * Consórcio: Kernel Engineer
 * Proibido innerHTML completo.
 * DocumentFragment para injeção cirúrgica (zero reflows/repaints).
 * renderDynamicFollowups() quando motor não retorna ui.actions.
 */
(function () {
    'use strict';

    const CONFIG = {
        MAX_CHIPS: 5,
        CHIP_RENDER_DEBOUNCE_MS: 150,
        STATE_UPDATE_DEBOUNCE_MS: 50,
        FRAGMENT_POOL_SIZE: 10,
        ANIMATION_DURATION_MS: 200,
        CHIPS_CONTAINER_ID: 'chatChips',
        CHAT_MESSAGES_ID: 'chatMessages'
    };

    /** Pool de DocumentFragment para reutilização (zero GC pressure) */
    class FragmentPool {
        constructor(size) {
            this._pool = [];
            for (let i = 0; i < size; i++) {
                this._pool.push(document.createDocumentFragment());
            }
        }
        acquire() {
            if (this._pool.length > 0) return this._pool.pop();
            return document.createDocumentFragment();
        }
        release(fragment) {
            while (fragment.firstChild) {
                fragment.removeChild(fragment.firstChild);
            }
            if (this._pool.length < CONFIG.FRAGMENT_POOL_SIZE) {
                this._pool.push(fragment);
            }
        }
    }

    const pool = new FragmentPool(CONFIG.FRAGMENT_POOL_SIZE);
    let chipDebounce = null;
    let stateDebounce = null;

    function createChipElement(label, action, regime) {
        const btn = document.createElement('button');
        btn.className = 'aura-chip aura-chip--' + (regime || 'neutral');
        btn.textContent = label;
        btn.dataset.action = action;
        btn.setAttribute('type', 'button');
        btn.addEventListener('click', function () {
            if (typeof window.__auraSendAction === 'function') {
                window.__auraSendAction(action, label);
            } else {
                window.dispatchEvent(new CustomEvent('aura:sidepanel-action', { detail: { action: action, label: label } }));
            }
        }, { passive: true });
        return btn;
    }

    /**
     * Renderiza chips contextuais baseados no regime quantitativo.
     * Usa DocumentFragment — zero reflow durante construção.
     */
    function renderDynamicFollowups(regime, context) {
        const container = document.getElementById(CONFIG.CHIPS_CONTAINER_ID);
        if (!container) return;

        const fragment = pool.acquire();
        const chips = buildChipsForRegime(regime, context || {});

        for (let i = 0; i < chips.length && i < CONFIG.MAX_CHIPS; i++) {
            fragment.appendChild(createChipElement(chips[i].label, chips[i].action, regime));
        }

        // Limpa e injeta em uma única operação (1 reflow)
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        container.appendChild(fragment);
        pool.release(fragment);
    }

    function buildChipsForRegime(regime, ctx) {
        const map = {
            'high_edge': [
                { label: 'Confirmar entrada', action: 'confirm_entry' },
                { label: 'Ajustar stake', action: 'adjust_stake' },
                { label: 'Ver Kelly', action: 'show_kelly' }
            ],
            'blocked_smd': [
                { label: 'Aguardar velocity', action: 'wait_velocity' },
                { label: 'Forçar análise', action: 'force_analysis' },
                { label: 'Histórico SMD', action: 'smd_history' }
            ],
            'cooldown': [
                { label: 'Status cooldown', action: 'cooldown_status' },
                { label: 'Próxima janela', action: 'next_window' }
            ],
            'neutral': [
                { label: 'Analisar agora', action: 'analyze_now' },
                { label: 'Status sistema', action: 'system_status' },
                { label: 'Últimos sinais', action: 'last_signals' }
            ],
            'low_prob': [
                { label: 'Recalcular Poisson', action: 'recalc_poisson' },
                { label: 'Mudar linha', action: 'change_line' }
            ]
        };
        return map[regime] || map['neutral'];
    }

    /**
     * Atualiza mensagem de chat sem innerHTML completo.
     * Apenas append de nós via DocumentFragment.
     */
    function appendMessage(role, text) {
        const container = document.getElementById(CONFIG.CHAT_MESSAGES_ID);
        if (!container) return;

        const fragment = pool.acquire();
        const div = document.createElement('div');
        div.className = 'aura-msg aura-msg--' + role;
        const span = document.createElement('span');
        span.textContent = text;  // textContent, nunca innerHTML
        div.appendChild(span);
        fragment.appendChild(div);
        container.appendChild(fragment);
        pool.release(fragment);
        container.scrollTop = container.scrollHeight;
    }

    /**
     * Ponto de entrada quando o motor responde.
     * Se não houver ui.actions, gera follow-ups dinâmicos.
     */
    function onMotorResponse(payload) {
        if (payload && payload.ui && Array.isArray(payload.ui.actions) && payload.ui.actions.length > 0) {
            // Usa actions do motor
            const container = document.getElementById(CONFIG.CHIPS_CONTAINER_ID);
            if (!container) return;
            const fragment = pool.acquire();
            payload.ui.actions.forEach(function (a) {
                fragment.appendChild(createChipElement(a.label || a, a.action || a, payload.regime));
            });
            while (container.firstChild) container.removeChild(container.firstChild);
            container.appendChild(fragment);
            pool.release(fragment);
        } else {
            // Fallback obrigatório
            const regime = (payload && payload.regime) || 'neutral';
            renderDynamicFollowups(regime, payload);
        }

        if (payload && payload.message) {
            appendMessage('assistant', payload.message);
        }
    }

    // API pública
    window.__auraSidepanel = {
        renderDynamicFollowups: renderDynamicFollowups,
        appendMessage: appendMessage,
        onMotorResponse: onMotorResponse
    };

    console.info('[AURA-UI] Pilar 7 (Sidepanel Dinâmica) ativo — DocumentFragment only');
})();
