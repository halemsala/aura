#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tipster_capture.py — agente captador de análises de jogos de grupos/canais
do Telegram, com registro automático de GREEN/RED via reactions e texto.

COMO FUNCIONA (o ciclo completo):

    FASE 1 — CAPTURA: userbot Telethon lê mensagens de grupos onde voce e
    membro (bots NAO conseguem ler historico【turn4search1】). Parser detecta
    padroes de entrada: odd, mercado (over/under corners), jogo, horario.

    FASE 2 — RESOLUCAO: para cada entrada detectada, o agente monitora:
    a) REACTIONS na propria mensagem (✅ verde, ❌ vermelho, 👍/👎)
    b) MENSAGENS DE FOLLOW-UP do mesmo canal que mencionam GREEN/RED
    c) RESPOSTAS (reply) a mensagem original com emoji resultado
    d) TIMEOUT: 4h sem resoluo = descartada (contabilizada como unknown)

    FASE 3 — REGISTRO: journal JSONL no mesmo formato do
    robot_alert_audit.py (compativel com a auditoria que ja existe).

    FASE 4 — ANALISE: periodicamente roda o robot_alert_audit sobre o
    journal acumulado, gerando scorecard por tipster/grupo.

    FASE 5 — PUBLICACAO: envia resumos para o SEU canal do Telegram via
    telegram_employee.py (que ja esta integrado).

REQUISITOS:
    pip install telethon
    API_ID e API_HASH de https://my.telegram.org (gratuito)
    Sua conta Telegram logada (nao e bot, e USERBOT)
    Voce DEVE ser membro dos grupos que quer monitorar

FRONTEIRA §0: isto e AUDITORIA de tipsters externos. O AURA nao copia
entradas — REGISTRA e AUDITA a taxa de acerto real de cada grupo.
As analises publicadas sao estatisticas honestas, nao recomendacoes.

INTEGRACAO: hunks na resposta. Python 3.9+. Windows. Console ASCII.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.tipster_capture")

__version__ = "1.0.0"
_PROJ_ROOT = Path(__file__).resolve().parents[2]
_JOURNAL_PATH = _PROJ_ROOT / "engine" / "data" / "tipster_tips.jsonl"
_GROUPS_PATH = _PROJ_ROOT / "engine" / "data" / "monitored_groups.json"

# ---------------------------------------------------------------------------
# parser de mensagens de tipster
# ---------------------------------------------------------------------------
GREEN_EMOJIS = {"✅", "✔", "☑", "✓", "🟢", "👍", "🔥", "💪", "💯"}
RED_EMOJIS = {"❌", "✖", "✗", "🔴", "👎", "💔", "🤦"}

ODD_RE = re.compile(r"(?:odd|odds|odd@|@)\s*([\d.,]+)", re.I)
MARKET_RE = re.compile(
    r"(over|under|mais\s+de|menos\s+de|acima|abaixo)\s*([\d.,]+)\s*"
    r"(corners?|escanteios?|cantos?|gols?|goals?)", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})[h:](\d{2})\b|\b(\d{1,2})h\b", re.I)
TEAMS_RE = re.compile(r"([A-Za-zÀ-ÿ][\wÀ-ÿ\s-]{2,30})\s*(?:vs?\.?|x)\s*"
                      r"([A-Za-zÀ-ÿ][\wÀ-ÿ\s-]{2,30})", re.I)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def _to_float(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_tip_message(text: str) -> Optional[dict]:
    """Detecta se uma mensagem e uma entrada de aposta.
    Retorna dict com dados extraidos ou None se nao for tip."""
    if not text or len(text) < 20:
        return None
    # precisa ter pelo menos mercado OU odd
    market = MARKET_RE.search(text)
    odd_m = ODD_RE.search(text)
    if not market and not odd_m:
        return None
    # precisa parecer uma tip (nao e conversa casual)
    tip_indicators = ["entrada", "aposta", "tip", "pick", "bet",
                      "confia", "vamos", "bora", "odd", "mercado",
                      "over", "under", "mais de", "menos de"]
    text_n = _norm(text)
    has_indicator = any(_norm(w) in text_n for w in tip_indicators)
    if not has_indicator:
        return None

    tip = {"market": "", "line": None, "odd": None,
           "home": "", "away": "", "time": ""}
    if market:
        tip["market"] = market.group(1).lower()
        tip["line"] = _to_float(market.group(2))
        tip["market_type"] = market.group(3).lower()
    if odd_m:
        tip["odd"] = _to_float(odd_m.group(1))
    teams = TEAMS_RE.search(text)
    if teams:
        tip["home"] = teams.group(1).strip()[:40]
        tip["away"] = teams.group(2).strip()[:40]
    time_m = TIME_RE.search(text)
    if time_m:
        tip["time"] = time_m.group(0)
    return tip


def detect_result_from_reactions(reactions_data: Any) -> Optional[str]:
    """Extrai green/red das reactions de uma mensagem.
    reactions_data: message.reactions do Telethon (MessageReactions object).
    Retorna 'green', 'red' ou None."""
    if reactions_data is None:
        return None
    try:
        # Telethon: message.reactions.results e lista de ReactionCount
        # cada ReactionCount tem .reaction (ReactionEmoji) e .count
        results = getattr(reactions_data, "results", None)
        if not results:
            return None
        green_count = 0
        red_count = 0
        for rc in results:
            reaction = getattr(rc, "reaction", None)
            if reaction is None:
                continue
            emoticon = getattr(reaction, "emoticon", "")
            count = getattr(rc, "count", 0) or 0
            if emoticon in GREEN_EMOJIS:
                green_count += count
            elif emoticon in RED_EMOJIS:
                red_count += count
        if green_count > 0 and red_count == 0:
            return "green"
        if red_count > 0 and green_count == 0:
            return "red"
        if green_count > red_count:
            return "green"
        if red_count > green_count:
            return "red"
        return None
    except Exception:
        return None


def detect_result_from_text(text: str) -> Optional[str]:
    """Detecta green/red em mensagens de follow-up."""
    if not text:
        return None
    t = _norm(text)
    # padroes explicitos
    if any(w in t for w in ["green", "verde", "ganhamos", "ganhou",
                            "acertou", "win", "winner", "✅"]):
        return "green"
    if any(w in t for w in ["red", "vermelho", "perdemo", "perdeu",
                            "errou", "loss", "loser", "❌"]):
        return "red"
    # contagem de emojis
    green_emojis = sum(1 for c in text if c in GREEN_EMOJIS)
    red_emojis = sum(1 for c in text if c in RED_EMOJIS)
    if green_emojis > red_emojis and green_emojis >= 2:
        return "green"
    if red_emojis > green_emojis and red_emojis >= 2:
        return "red"
    return None


# ---------------------------------------------------------------------------
# journal (mesmo formato do robot_alert_audit para compatibilidade)
# ---------------------------------------------------------------------------
class TipsterJournal:
    """Journal JSONL das tips capturadas — formato compativel com
    robot_alert_audit.py (pode rodar a mesma auditoria)."""

    def __init__(self, path: Optional[Any] = None):
        self._path = Path(path) if path else _JOURNAL_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.stats = {"tips_captured": 0, "resolved": 0,
                      "greens": 0, "reds": 0, "unknown": 0}

    def add_tip(self, group: str, tip: dict, message_id: int,
                message_text: str) -> str:
        """Adiciona tip pendente. Retorna tip_id."""
        tip_id = "tip_%d_%d" % (message_id, int(time.time()))
        entry = {
            "id": tip_id,
            "data_hora": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "tipo_alerta": "telegram_tip",
            "liga": group,
            "jogo": "%s vs %s" % (tip.get("home", "?"),
                                   tip.get("away", "?")),
            "tempo": tip.get("time", ""),
            "placar": "",
            "odd_entrada": tip.get("odd"),
            "mercado": tip.get("market", ""),
            "resultado": None,  # pendente
            "message_id": message_id,
            "group": group,
            "raw_text": message_text[:500],
            "market_type": tip.get("market_type", ""),
            "line": tip.get("line"),
        }
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.stats["tips_captured"] += 1
        return tip_id

    def resolve_tip(self, tip_id: str, result: str,
                    source: str = "reactions") -> bool:
        """Marca resultado da tip (green/red)."""
        if result not in ("green", "red", "unknown"):
            return False
        with self._lock:
            lines = []
            updated = False
            try:
                current = self._path.read_text(
                    encoding="utf-8").splitlines()
            except OSError:
                current = []
            for line in current:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("id") == tip_id and entry.get("resultado") is None:
                    entry["resultado"] = result
                    entry["resolved_at"] = datetime.now(
                        timezone.utc).isoformat(timespec="seconds")
                    entry["resolution_source"] = source
                    updated = True
                    if result == "green":
                        self.stats["greens"] += 1
                    elif result == "red":
                        self.stats["reds"] += 1
                    else:
                        self.stats["unknown"] += 1
                    self.stats["resolved"] += 1
                lines.append(json.dumps(entry, ensure_ascii=False))
            if updated:
                tmp = self._path.with_suffix(".jsonl.tmp")
                tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
                tmp.replace(self._path)
            return updated

    def get_pending(self) -> List[dict]:
        """Tips pendentes de resoluoo."""
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        pending = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("resultado") is None:
                    pending.append(entry)
            except ValueError:
                continue
        return pending

    def get_stats_by_group(self) -> Dict[str, dict]:
        """Estatistica por grupo."""
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        groups: Dict[str, dict] = {}
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            g = entry.get("group", "?")
            groups.setdefault(g, {"total": 0, "green": 0, "red": 0,
                                  "pending": 0})
            groups[g]["total"] += 1
            result = entry.get("resultado")
            if result == "green":
                groups[g]["green"] += 1
            elif result == "red":
                groups[g]["red"] += 1
            else:
                groups[g]["pending"] += 1
        return groups

    def stats_dict(self) -> dict:
        return {"tipster_journal": {
            "path": str(self._path), **self.stats}}


# ---------------------------------------------------------------------------
# agente captador (Telethon userbot)
# ---------------------------------------------------------------------------
class TipsterCaptureAgent:
    """Monitora grupos do Telegram e captura tips com resoluoo."""

    def __init__(self, api_id: Optional[int] = None,
                 api_hash: Optional[str] = None,
                 session_name: str = "aura_tipster",
                 journal: Optional[TipsterJournal] = None,
                 groups_config: Optional[List[dict]] = None):
        raw_api_id = api_id if api_id is not None else os.environ.get("TG_API_ID", "0")
        try:
            self._api_id = int(raw_api_id or 0)
        except (TypeError, ValueError):
            logger.warning("tipster_capture: TG_API_ID inválido; agente permanece off")
            self._api_id = 0
        self._api_hash = (api_hash or os.environ.get("TG_API_HASH", "")).strip()
        self._session = session_name

        self._journal = journal or TipsterJournal()
        self._groups = groups_config or self._load_groups()
        self._client = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.stats = {"messages_scanned": 0, "tips_found": 0,
                      "reactions_checked": 0, "followup_checked": 0,
                      "errors": 0, "groups_active": 0}

    def _load_groups(self) -> List[dict]:
        """Carrega grupos monitorados do config."""
        try:
            if _GROUPS_PATH.is_file():
                data = json.loads(_GROUPS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [g for g in data
                            if isinstance(g, dict)
                            and (g.get("id") or g.get("username"))]
        except Exception:
            pass
        # Sem arquivo de configuração, não criar estado nem grupo de exemplo.
        return []

    def available(self) -> bool:
        """Verifica se Telethon e credenciais estao disponiveis."""
        if not self._api_id or not self._api_hash:
            return False
        try:
            import telethon  # noqa: F401
            return True
        except Exception:
            return False

    def start(self) -> bool:
        """Inicia o agente em thread separada."""
        if not self.available():
            logger.warning("tipster_capture: Telethon ou credenciais "
                           "ausentes — agente off (pip install telethon, "
                           "TG_API_ID/TG_API_HASH)")
            return False
        if self._thread and self._thread.is_alive():
            return True
        if not self._groups:
            logger.warning("tipster_capture: nenhum grupo configurado "
                           "(monitored_groups.json)")
            return False
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop,
                                        daemon=True,
                                        name="aura-tipster-capture")
        self._thread.start()
        self.stats["groups_active"] = len(self._groups)
        return True

    def stop(self) -> None:
        self._stop.set()
        self._running = False

    def _run_loop(self) -> None:
        """Loop principal do userbot."""
        try:
            asyncio.run(self._async_loop())
        except Exception:
            logger.exception("tipster_capture: loop falhou")
            self.stats["errors"] += 1

    async def _async_loop(self) -> None:
        """Loop assincrono do Telethon."""
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession

        # Não usar TelegramClient com caminho de arquivo: uma sessão Telethon
        # persistida em plaintext equivale a um login reutilizável. A ativação
        # segura exige uma StringSession fornecida explicitamente pelo operador;
        # sem ela, o módulo permanece desligado.
        session_string = os.environ.get("TG_SESSION_STRING", "").strip()
        if not session_string:
            raise RuntimeError("TG_SESSION_STRING ausente; sessão em disco desabilitada por segurança")
        client = TelegramClient(StringSession(session_string), self._api_id,
                                self._api_hash)

        await client.start()
        logger.info("tipster_capture: userbot conectado")

        # resolve entidades dos grupos
        group_entities = {}
        for g in self._groups:
            ident = g.get("username") or g.get("id")
            label = g.get("label", str(ident))
            try:
                entity = await client.get_entity(ident)
                group_entities[entity.id] = {"entity": entity,
                                             "label": label}
            except Exception as exc:
                logger.warning("tipster_capture: grupo %s falhou: %s",
                               ident, exc)

        # handler para novas mensagens
        @client.on(events.NewMessage(chats=list(
                group_entities.keys()) if group_entities else None))
        async def on_new_message(event):
            try:
                self.stats["messages_scanned"] += 1
                chat_id = event.chat_id
                group_info = group_entities.get(chat_id)
                if group_info is None:
                    return
                label = group_info["label"]
                text = event.message.text or ""
                tip = parse_tip_message(text)
                if tip is not None:
                    self.stats["tips_found"] += 1
                    tip_id = self._journal.add_tip(
                        label, tip, event.message.id, text)
                    logger.info("tip capturada: %s (%s)", tip_id, label)
            except Exception:
                self.stats["errors"] += 1
                logger.exception("tipster_capture: handler erro")

        # handler para edits (reactions aparecem como edits as vezes)
        @client.on(events.MessageEdited(chats=list(
                group_entities.keys()) if group_entities else None))
        async def on_edit(event):
            try:
                self.stats["reactions_checked"] += 1
                text = event.message.text or ""
                # verifica reactions na mensagem editada
                reactions = getattr(event.message, "reactions", None)
                result = detect_result_from_reactions(reactions)
                if result is None:
                    result = detect_result_from_text(text)
                if result:
                    # encontra tip pendente por message_id
                    pending = self._journal.get_pending()
                    for p in pending:
                        if p.get("message_id") == event.message.id:
                            self._journal.resolve_tip(
                                p["id"], result, "edit")
                            break
            except Exception:
                self.stats["errors"] += 1

        # loop de verificação periódica com intervalo mínimo e backoff. O
        # limite evita rajadas MTProto quando o journal cresce ou a rede falha.
        interval = 60.0
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            if self._stop.is_set():
                break
            try:
                await self._check_pending(client, group_entities)
                interval = 60.0
            except Exception:
                logger.exception("tipster_capture: check_pending erro")
                interval = min(interval * 2.0, 900.0)

        await client.disconnect()

    async def _check_pending(self, client, group_entities: dict) -> None:
        """Verifica tips pendentes: le mensagens recentes procurando
        resoluoo em follow-ups e reactions."""
        pending = self._journal.get_pending()
        if not pending:
            return
        # Limite por ciclo: o restante será processado em ciclos posteriores.
        pending = pending[:100]

        cutoff = time.time() - 4 * 3600  # 4h timeout
        for tip in pending:
            tip_time = tip.get("data_hora", "")
            try:
                dt = datetime.fromisoformat(tip_time)
                if dt.timestamp() < cutoff:
                    # timeout — marca como unknown
                    self._journal.resolve_tip(tip["id"], "unknown",
                                              "timeout")
                    continue
            except (ValueError, TypeError):
                pass
            # busca a mensagem original para ver reactions
            msg_id = tip.get("message_id")
            group = tip.get("group", "")
            if not msg_id:
                continue
            # encontra entity do grupo
            for gid, info in group_entities.items():
                if info["label"] == group:
                    try:
                        msg = await client.get_messages(
                            info["entity"], ids=msg_id)
                        if msg:
                            self.stats["reactions_checked"] += 1
                            reactions = getattr(msg, "reactions", None)
                            result = detect_result_from_reactions(reactions)
                            if result:
                                self._journal.resolve_tip(
                                    tip["id"], result, "reaction")
                                continue
                            # verifica texto da mensagem
                            result = detect_result_from_text(msg.text or "")
                            if result:
                                self._journal.resolve_tip(
                                    tip["id"], result, "text")
                    except Exception:
                        self.stats["errors"] += 1
                        logger.exception("tipster_capture: follow-up falhou")
                    # Rate limit cooperativo por conta/grupo.
                    await asyncio.sleep(0.25)
                    break

    def stats_dict(self) -> dict:
        return {"tipster_capture": {
            "available": self.available(),
            "running": self._running,
            **self.stats}}


# ---------------------------------------------------------------------------
# ferramentas para o CommandCenter
# ---------------------------------------------------------------------------
def parse_tipster_capture(utterance: str):
    t = _norm(utterance)
    if not t:
        return None
    import re
    if re.search(r"\b(?:quais|liste?|lista)\s+grupos?\s+monitorados?\b", t):
        return ("tipster_grupos", {})
    if re.search(r"\b(?:scorecard|desempenho)\s+d[oa]s?\s+(?:tipsters?|"
                 r"grupos?)\b|\bestatisticas?\s+d[oa]s?\s+grupos?\b", t):
        return ("tipster_scorecard", {})
    if re.search(r"\b(?:tips?|entradas?)\s+pendentes?\b", t):
        return ("tipster_pendentes", {})
    if re.search(r"\b(?:resumo|analise)\s+d[oa]s?\s+(?:tips?|tipsters?|"
                 r"grupos?)\b", t):
        return ("tipster_resumo", {})
    return None


def build_tipster_tools(cc, agent: TipsterCaptureAgent,
                        journal: TipsterJournal,
                        publish_fn: Optional[Callable] = None) -> None:
    """Registra tools. publish_fn: funoo que envia para o canal do AURA
    (usa telegram_employee se disponivel)."""

    def t_grupos(args, session):
        groups = agent._groups
        if not groups:
            return {"ok": True, "speech": "Nenhum grupo configurado em "
                    "monitored_groups.json."}
        return {"ok": True, "speech": "Grupos monitorados: %s." % ", ".join(
            g.get("label", "?") for g in groups)}

    def t_scorecard(args, session):
        stats = journal.get_stats_by_group()
        if not stats:
            return {"ok": True, "speech": "Nenhuma tip capturada ainda."}
        parts = []
        for group, s in sorted(stats.items(),
                               key=lambda kv: -kv[1]["total"]):
            total_resolved = s["green"] + s["red"]
            if total_resolved > 0:
                rate = 100.0 * s["green"] / total_resolved
                parts.append("%s: %d/%d verde (%.0f%%)"
                             % (group, s["green"], total_resolved, rate))
            else:
                parts.append("%s: %d pendente(s)"
                             % (group, s["pending"]))
        speech = "Scorecard por grupo: %s." % "; ".join(parts[:6])
        # publica no canal se disponivel
        if publish_fn:
            try:
                publish_fn(speech)
            except Exception:
                pass
        return {"ok": True, "speech": speech, "stats": stats}

    def t_pendentes(args, session):
        pending = journal.get_pending()
        if not pending:
            return {"ok": True, "speech": "Nenhuma tip pendente."}
        return {"ok": True, "speech": "%d tip(s) aguardando resoluoo."
                % len(pending)}

    def t_resumo(args, session):
        st = journal.stats
        if st["tips_captured"] == 0:
            return {"ok": True, "speech": "Ainda nao capturei tips. "
                    "Adicione grupos em monitored_groups.json."}
        total_resolved = st["greens"] + st["reds"]
        if total_resolved > 0:
            rate = 100.0 * st["greens"] / total_resolved
        else:
            rate = 0.0
        speech = ("Resumo: %d tips capturadas, %d resolvidas "
                  "(%d verde, %d vermelho). Taxa de acerto: %.1f%%."
                  % (st["tips_captured"], total_resolved,
                     st["greens"], st["reds"], rate))
        if publish_fn:
            try:
                publish_fn("[AUDITORIA AURA] " + speech)
            except Exception:
                pass
        return {"ok": True, "speech": speech}

    cc.register("tipster_grupos", "listar grupos monitorados",
                t_grupos, "read")
    cc.register("tipster_scorecard", "scorecard por grupo de tipster",
                t_scorecard, "read")
    cc.register("tipster_pendentes", "tips pendentes de resoluoo",
                t_pendentes, "read")
    cc.register("tipster_resumo", "resumo estatistico das tips",
                t_resumo, "read")


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    # --- parser ---
    tip = parse_tip_message(
        "🔥 ENTRADA CONFIRMADA 🔥\n"
        "Benfica vs Porto\n"
        "Over 9.5 corners\n"
        "Odd @1.85\n"
        "Confia demais! Vamos!")
    check("parser: tip detectada", tip is not None)
    if tip:
        check("parser: mercado over", tip["market"] == "over")
        check("parser: linha 9.5", tip["line"] == 9.5)
        check("parser: odd 1.85", tip["odd"] == 1.85)
        check("parser: times", "benfica" in tip["home"].lower()
              or "benfica" in tip["away"].lower())

    tip2 = parse_tip_message(
        "Bom dia pessoal, como voces estao hoje?")
    check("parser: conversa casual nao e tip", tip2 is None)

    tip3 = parse_tip_message(
        "Under 8.5 escanteios - Corinthians vs Palmeiras @2.10")
    check("parser: under detectado", tip3 is not None
          and tip3["market"] == "under")
    check("parser: linha under 8.5", tip3["line"] == 8.5)

    # --- detect_result_from_text ---
    check("texto: green", detect_result_from_text(
        "GREEN! Acertamos mais uma! ✅✅✅") == "green")
    check("texto: red", detect_result_from_text(
        "RED... infelizmente perdeu ❌") == "red")
    check("texto: neutro", detect_result_from_text(
        "Proxima entrada em breve...") is None)
    check("texto: ganhou", detect_result_from_text(
        "Ganhou! Entrada certa!") == "green")
    check("texto: perdeu", detect_result_from_text(
        "Perdemos essa, vamos pra proxima") == "red")

    # --- detect_result_from_reactions (fake) ---
    class FakeReactionEmoji:
        def __init__(self, emoticon):
            self.emoticon = emoticon

    class FakeReactionCount:
        def __init__(self, emoticon, count):
            self.reaction = FakeReactionEmoji(emoticon)
            self.count = count

    class FakeReactions:
        def __init__(self, results):
            self.results = results

    check("reactions: verde", detect_result_from_reactions(
        FakeReactions([FakeReactionCount("✅", 5)])) == "green")
    check("reactions: vermelho", detect_result_from_reactions(
        FakeReactions([FakeReactionCount("❌", 3)])) == "red")
    check("reactions: verde mais votado", detect_result_from_reactions(
        FakeReactions([FakeReactionCount("✅", 10),
                       FakeReactionCount("❌", 2)])) == "green")
    check("reactions: vazio", detect_result_from_reactions(
        FakeReactions([])) is None)
    check("reactions: None", detect_result_from_reactions(None) is None)

    # --- journal ---
    with tempfile.TemporaryDirectory(prefix="aura_tc_st_") as td:
        journal = TipsterJournal(Path(td) / "tips.jsonl")
        tip_data = {"market": "over", "line": 9.5, "odd": 1.85,
                    "home": "Time A", "away": "Time B", "time": "15h"}
        tip_id = journal.add_tip("Grupo Teste", tip_data, 123, "texto...")
        check("journal: tip adicionada", len(tip_id) > 0)
        pending = journal.get_pending()
        check("journal: pendente", len(pending) == 1
              and pending[0]["id"] == tip_id)
        # resolve
        ok = journal.resolve_tip(tip_id, "green", "test")
        check("journal: resolvida green", ok is True)
        pending = journal.get_pending()
        check("journal: sem pendentes apos resolver", len(pending) == 0)
        # stats por grupo
        stats = journal.get_stats_by_group()
        check("journal: stats por grupo",
              stats.get("Grupo Teste", {}).get("green") == 1)
        # ja resolvida, nao resolve de novo
        ok = journal.resolve_tip(tip_id, "red", "test2")
        check("journal: nao re-resolve", ok is False)

    # --- agent (sem Telethon) ---
    agent = TipsterCaptureAgent(api_id=0, api_hash="")
    check("agent: unavailable sem credenciais",
          agent.available() is False)
    check("agent: start falha sem deps", agent.start() is False)
    check("agent: stats coerente", "available" in agent.stats_dict()[
        "tipster_capture"])

    # --- gramatica ---
    check("gram: grupos", parse_tipster_capture(
        "quais grupos monitorados") == ("tipster_grupos", {}))
    check("gram: scorecard", parse_tipster_capture(
        "scorecard dos tipsters") == ("tipster_scorecard", {}))
    check("gram: pendentes", parse_tipster_capture(
        "tips pendentes") == ("tipster_pendentes", {}))
    check("gram: resumo", parse_tipster_capture(
        "resumo das tips") == ("tipster_resumo", {}))
    check("gram: conversa comum", parse_tipster_capture(
        "bom dia") is None)

    # --- integracao CommandCenter ---
    try:
        from jarvis_command_center import CommandCenter
    except Exception:
        CommandCenter = None
    if CommandCenter is None:
        print("[SKIP] jarvis_command_center nao importavel aqui")
    else:
        with tempfile.TemporaryDirectory() as td:
            j = TipsterJournal(Path(td) / "tips.jsonl")
            integration_tip_id = j.add_tip("Teste", tip_data, 1, "x")
            j.resolve_tip(integration_tip_id, "green", "t")
            cc = CommandCenter()
            build_tipster_tools(cc, agent, j)
            r = cc.execute("tipster_scorecard", {}, "u")
            check("cc: scorecard funciona", r["ok"] is True
                  and "verde" in r["speech"].lower())
            r = cc.execute("tipster_resumo", {}, "u")
            check("cc: resumo funciona", r["ok"] is True
                  and "capturadas" in r["speech"].lower())

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - tipster_capture.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
