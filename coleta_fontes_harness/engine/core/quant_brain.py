import math
import hashlib
import logging
logger = logging.getLogger("aura.quant_brain")
class QuantBrain:
    def __init__(self):
        self.last_valid_state = None
    def process_telemetry(self, payload: dict) -> dict:
        try:
            def _num(value, default=0.0):
                if value is None or value == "":
                    return default
                return float(value)

            minute = _num(payload.get("minute"), 0.0)
            corners_now = int(_num(payload.get("corners"), 0.0))
            xg = _num(payload.get("xG"), 0.0)
            pressure = _num(payload.get("pressure"), 0.0)
            danger = int(_num(payload.get("dangerous_attacks"), 0.0))
           
            if minute <= 0: return {"action": "IGNORE_SILENT", "reason": "Jogo não começou"}
            if self.last_valid_state:
                delta_xg = abs(xg - self.last_valid_state['xg'])
                delta_pressure = abs(pressure - self.last_valid_state['pressure'])
                if delta_xg < 0.05 and delta_pressure < 10.0 and corners_now == self.last_valid_state['corners']:
                    return {"action": "IGNORE_SILENT", "reason": "Ruído estatístico filtrado"}
            # Rolling pressure (se o caller injetou feats no payload)
            try:
                p_delta = float(payload.get("pressure_delta", 0) or 0)
                dang_r = float(payload.get("dang_rate_10m", 0) or 0)
                if payload.get("is_noise") or (abs(p_delta) < 5.0 and dang_r < 0.05 and self.last_valid_state
                        and corners_now == self.last_valid_state.get("corners")):
                    return {
                        "action": "IGNORE_SILENT",
                        "reason": "Ruído: pressão/ataques rolantes estáveis",
                        "pressure_ma": payload.get("pressure_ma"),
                        "pressure_delta": p_delta,
                        "dang_rate_10m": dang_r,
                    }
            except (TypeError, ValueError):
                pass
            danger_rate = danger / max(minute, 1)
            imc = (danger_rate * 10) * (xg * 5) * (pressure / 100)
            imc = round(imc, 2)
            corner_rate = corners_now / max(minute, 1)
            imc_bucket = round(imc, 1)
            corner_status = "HIGH" if corner_rate > 0.15 else "LOW"
            situation_id = f"IMC{imc_bucket}_{corner_status}_MIN{int(minute//15)}"
            hash_id = hashlib.md5(situation_id.encode()).hexdigest()
            historical_prob = self._check_pattern_hash(hash_id)
            if historical_prob is not None:
                return {"action": "PATTERN_MATCH", "reason": f"Padrão histórico (visto {historical_prob['occurrences']}x)", "probabilidade_historica": historical_prob['prob'], "imc": imc}
            delta_info = ""
            if self.last_valid_state:
                delta_imc = imc - self.last_valid_state.get('imc', imc)
                delta_info = f"IMC mudou {delta_imc:+.2f}."
            self.last_valid_state = {"xg": xg, "pressure": pressure, "corners": corners_now, "imc": imc}
            return {"action": "NEEDS_AI", "reason": f"Anomalia relevante. {delta_info}", "imc": imc, "corner_rate": corner_rate, "compressed_context": f"IMC: {imc}. Taxa Corner: {corner_rate:.2f}/min. Minuto: {minute}."}
        except Exception as e:
            logger.error(f"Erro no Quant Brain: {e}")
            return {"action": "NEEDS_AI", "reason": "Fallback de segurança", "raw_payload": payload}
    def _check_pattern_hash(self, hash_id: str):
        try:
            # Tenta usar a conexão thread-safe do V23, se não existir, usa sqlite3 bruto
            try:
                from engine.data_store import get_thread_safe_conn
                conn = get_thread_safe_conn()
            except ImportError:
                import sqlite3
                conn = sqlite3.connect('engine/aura_quant_x.db')
               
            cursor = conn.cursor()
            cursor.execute("SELECT occurrences, corners_happened FROM pattern_fingerprints WHERE hash_id=?", (hash_id,))
            row = cursor.fetchone()
            if row:
                occ, happened = row
                prob = (happened / occ) * 100 if occ > 0 else 0
                return {"occurrences": occ, "prob": round(prob, 1)}
            return None
        except Exception:
            return None

# V25 compatibility: server imports `quant_brain` instance
quant_brain = QuantBrain()
