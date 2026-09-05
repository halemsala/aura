# engine/hybrid_data_store.py
"""
Módulo de Persistência Híbrida de Ultra-Alta Velocidade - AURA QUANT-X v12.6.17
Implementa Double-Buffering Ring Buffer com flush assíncrono para disco.
Autor: Consórcio AURA QUANT-X (Chief Quant Architect + Kernel Engineer)
"""

import sqlite3
import threading
import time
import os
import json
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# Configuração de logging estruturado
logger = logging.getLogger("aura.hybrid_store")

# Constantes de configuração do buffer
BUFFER_SIZE_LIMIT = 10000  # Número máximo de registros antes do flush
FLUSH_INTERVAL_SECONDS = 60.0  # Intervalo máximo entre flushes
BUFFER_SLOT_COUNT = 10050  # Tamanho físico do array circular (margem de segurança)


class RingBuffer:
    """
    Buffer circular de tamanho fixo para armazenamento temporário de registros.
    Implementa semântica de sobrescrita quando cheio (ring) com rastreabilidade.
    """
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._buffer: List[Optional[Dict[str, Any]]] = [None] * capacity
        self._write_index: int = 0
        self._count: int = 0
        self._index_by_correlation: OrderedDict[str, int] = OrderedDict()
        self._max_correlation_cache = 5000  # Limita cache para controlar memória
    
    def push(self, record: Dict[str, Any]) -> bool:
        """
        Insere um registro no buffer circular.
        Retorna True se inseriu, False se buffer estava cheio e sobrescreveu.
        """
        correlation_id = record.get("correlation_id", "")
        
        # Remove entrada antiga do índice se vamos sobrescrever
        if self._count >= self.capacity:
            old_index = (self._write_index) % self.capacity
            old_record = self._buffer[old_index]
            if old_record and old_record.get("correlation_id"):
                old_corr = old_record["correlation_id"]
                if old_corr in self._index_by_correlation:
                    del self._index_by_correlation[old_corr]
        
        # Insere no buffer
        self._buffer[self._write_index] = record
        self._write_index = (self._write_index + 1) % self.capacity
        self._count = min(self._count + 1, self.capacity)
        
        # Atualiza índice de correlação
        if correlation_id:
            self._index_by_correlation[correlation_id] = self._write_index - 1
            # Evita crescimento descontrolado do índice
            if len(self._index_by_correlation) > self._max_correlation_cache:
                self._index_by_correlation.popitem(last=False)
        
        return self._count <= self.capacity
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Retorna todos os registros válidos em ordem de inserção."""
        if self._count == 0:
            return []
        if self._count < self.capacity:
            return [r for r in self._buffer[:self._count] if r is not None]
        # Buffer cheio: retorna a partir do write_index (mais antigo) até write_index-1
        result = []
        for i in range(self.capacity):
            idx = (self._write_index + i) % self.capacity
            if self._buffer[idx] is not None:
                result.append(self._buffer[idx])
        return result
    
    def clear(self) -> int:
        """Limpa o buffer e retorna a quantidade de registros que havia."""
        count = self._count
        self._buffer = [None] * self.capacity
        self._write_index = 0
        self._count = 0
        self._index_by_correlation.clear()
        return count
    
    @property
    def count(self) -> int:
        return self._count
    
    def find_by_correlation(self, correlation_id: str) -> Optional[Dict[str, Any]]:
        """Busca rápida por correlation_id usando índice."""
        if not correlation_id or correlation_id not in self._index_by_correlation:
            return None
        idx = self._index_by_correlation[correlation_id]
        return self._buffer[idx % self.capacity]


class HybridDataStore:
    """
    Store híbrido com banco em RAM e flush assíncrono para disco.
    Implementa Double-Buffering para eliminação completa de I/O síncrono.
    """
    
    SCHEMA_VERSION = "12.6.17"
    
    def __init__(self, db_disk_path: str, buffer_size: int = BUFFER_SIZE_LIMIT):
        """
        Inicializa o store híbrido.
        
        Args:
            db_disk_path: Caminho absoluto para o banco de dados em disco
            buffer_size: Tamanho limite do buffer antes de forçar flush
        """
        self._db_disk_path = db_disk_path
        self._buffer_size = buffer_size
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None
        self._flush_count = 0
        self._error_count = 0
        self._last_flush_time: float = 0.0
        self._total_records_inserted = 0
        self._total_records_flushed = 0
        
        # Double-buffer: active é para escrita, staging é para flush
        self._active_buffer = RingBuffer(BUFFER_SLOT_COUNT)
        self._staging_buffer: Optional[RingBuffer] = None
        
        # Inicializa banco em RAM
        self._ram_conn = self._create_ram_database()
        
        # Inicializa conexão para disco (lazy)
        self._disk_conn: Optional[sqlite3.Connection] = None
        
        logger.info(
            f"HybridDataStore inicializado | buffer_size={buffer_size} | "
            f"db_path={db_disk_path}"
        )
    
    def _create_ram_database(self) -> sqlite3.Connection:
        """Cria e retorna conexão com banco SQLite em memória."""
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=0")
        self._create_schema(conn)
        logger.debug("Banco de dados em RAM criado com sucesso")
        return conn
    
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Cria o schema completo do banco de dados."""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS logs_telemetria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                fixture_id TEXT,
                home_team TEXT,
                away_team TEXT,
                match_minute INTEGER,
                score_home INTEGER DEFAULT 0,
                score_away INTEGER DEFAULT 0,
                corners_home INTEGER DEFAULT 0,
                corners_away INTEGER DEFAULT 0,
                dangerous_attacks_home INTEGER DEFAULT 0,
                dangerous_attacks_away INTEGER DEFAULT 0,
                xg_home REAL DEFAULT 0.0,
                xg_away REAL DEFAULT 0.0,
                pressure_home REAL DEFAULT 0.0,
                pressure_away REAL DEFAULT 0.0,
                corner_prob REAL,
                signal_decision TEXT,
                edge REAL,
                kelly_fraction REAL,
                asian_corner_line REAL,
                asian_corner_odds REAL,
                odds_velocity REAL,
                correlation_id TEXT,
                data_integrity TEXT,
                raw_payload TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_telemetry_fixture 
                ON logs_telemetria(fixture_id);
            CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp 
                ON logs_telemetria(timestamp);
            CREATE INDEX IF NOT EXISTS idx_telemetry_correlation 
                ON logs_telemetria(correlation_id);
            CREATE INDEX IF NOT EXISTS idx_telemetry_signal 
                ON logs_telemetria(signal_decision);
            
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                signal_decision TEXT NOT NULL,
                corner_prob REAL,
                triggered_at TEXT NOT NULL,
                outcome TEXT,
                resolved_at TEXT,
                profit_loss REAL DEFAULT 0.0,
                correlation_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_outcomes_fixture 
                ON signal_outcomes(fixture_id);
            CREATE INDEX IF NOT EXISTS idx_outcomes_pending 
                ON signal_outcomes(outcome) WHERE outcome IS NULL;
            
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id TEXT NOT NULL,
                trade_id TEXT NOT NULL UNIQUE,
                signal_decision TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                entry_corner_line REAL,
                entry_odds REAL,
                stake REAL NOT NULL,
                kelly_fraction REAL,
                exit_time TEXT,
                exit_corner_line REAL,
                exit_odds REAL,
                outcome TEXT,
                profit_loss REAL DEFAULT 0.0,
                risk_reason_code TEXT,
                correlation_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_trades_fixture 
                ON paper_trades(fixture_id);
            CREATE INDEX IF NOT EXISTS idx_trades_open 
                ON paper_trades(outcome) WHERE outcome IS NULL;
            CREATE INDEX IF NOT EXISTS idx_trades_date 
                ON paper_trades(entry_time);
            
            CREATE TABLE IF NOT EXISTS risk_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                calibration_date TEXT NOT NULL,
                parameter_name TEXT NOT NULL,
                old_value REAL,
                new_value REAL,
                reason TEXT,
                correlation_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_level TEXT NOT NULL DEFAULT 'INFO',
                message TEXT,
                details TEXT,
                correlation_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_events_type 
                ON system_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_time 
                ON system_events(created_at);
        """)
        
        # Registra versão do schema
        try:
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (self.SCHEMA_VERSION,)
            )
        except sqlite3.Error:
            pass
        
        conn.commit()
        logger.debug("Schema do banco de dados criado/verificado")
    
    def _get_disk_connection(self) -> sqlite3.Connection:
        """Retorna conexão com banco em disco, criando se necessário."""
        if self._disk_conn is None:
            db_dir = os.path.dirname(self._db_disk_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            self._disk_conn = sqlite3.connect(
                self._db_disk_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._disk_conn.row_factory = sqlite3.Row
            self._disk_conn.execute("PRAGMA journal_mode=WAL")
            self._disk_conn.execute("PRAGMA synchronous=NORMAL")
            self._disk_conn.execute("PRAGMA wal_autocheckpoint=1000")
            self._disk_conn.execute("PRAGMA busy_timeout=5000")
            self._create_schema(self._disk_conn)
            logger.info(f"Conexão com disco estabelecida: {self._db_disk_path}")
        
        return self._disk_conn
    
    def start(self) -> None:
        """Inicia a thread de flush assíncrono."""
        if self._flush_thread is not None and self._flush_thread.is_alive():
            logger.warning("Thread de flush já está em execução")
            return
        
        self._shutdown_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_worker,
            name="HybridStore-FlushDaemon",
            daemon=True
        )
        self._flush_thread.start()
        logger.info("Thread de flush assíncrono iniciada")
    
    def stop(self, wait_flush: bool = True) -> None:
        """Para a thread de flush e opcionalmente aguarda flush final."""
        self._shutdown_event.set()
        if self._flush_thread is not None:
            if wait_flush:
                self._flush_thread.join(timeout=10.0)
            self._flush_thread = None
        self._force_flush()
        if self._disk_conn is not None:
            try:
                self._disk_conn.close()
            except sqlite3.Error:
                pass
            self._disk_conn = None
        logger.info(
            f"HybridDataStore parado | flushes={self._flush_count} | "
            f"errors={self._error_count} | total_inserted={self._total_records_inserted} | "
            f"total_flushed={self._total_records_flushed}"
        )
    
    def _flush_worker(self) -> None:
        """
        Worker daemon que realiza flush periódico do buffer para disco.
        Opera em loop até receber sinal de shutdown.
        """
        logger.debug("Worker de flush iniciado")
        while not self._shutdown_event.is_set():
            # Aguarda intervalo ou shutdown
            self._shutdown_event.wait(timeout=FLUSH_INTERVAL_SECONDS)
            
            if self._shutdown_event.is_set():
                # Flush final antes de sair
                self._force_flush()
                break
            
            # Verifica se precisa fazer flush por tamanho
            should_flush = False
            with self._lock:
                if self._active_buffer.count >= self._buffer_size:
                    should_flush = True
            
            if should_flush:
                self._force_flush()
        
        logger.debug("Worker de flush finalizado")
    
    def _force_flush(self) -> int:
        """
        Realiza flush imediato do buffer ativo para disco.
        Retorna o número de registros persistidos.
        """
        records_to_flush: List[Dict[str, Any]] = []
        
        with self._lock:
            if self._active_buffer.count == 0:
                return 0
            
            # Swap atômico de buffers
            self._staging_buffer = self._active_buffer
            self._active_buffer = RingBuffer(BUFFER_SLOT_COUNT)
            records_to_flush = self._staging_buffer.get_all()
            self._staging_buffer.clear()
            self._staging_buffer = None
        
        if not records_to_flush:
            return 0
        
        # Flush fora do lock - operação em disco não bloqueia escritas
        flushed = self._write_batch_to_disk(records_to_flush)
        self._flush_count += 1
        self._last_flush_time = time.time()
        self._total_records_flushed += flushed
        
        logger.debug(
            f"Flush #{self._flush_count} | registros={flushed}/{len(records_to_flush)} | "
            f"buffer_ativo={self._active_buffer.count}"
        )
        
        return flushed
    
    def _write_batch_to_disk(self, records: List[Dict[str, Any]]) -> int:
        """
        Escreve lote de registros no banco de dados em disco.
        Usa transação isolada para garantir atomicidade.
        """
        if not records:
            return 0
        
        disk_conn = self._get_disk_connection()
        flushed = 0
        
        try:
            disk_conn.execute("BEGIN IMMEDIATE TRANSACTION")
            
            for record in records:
                record_type = record.get("_record_type", "telemetry")
                
                if record_type == "telemetry":
                    self._insert_telemetry_disk(disk_conn, record)
                    flushed += 1
                elif record_type == "outcome":
                    self._insert_outcome_disk(disk_conn, record)
                    flushed += 1
                elif record_type == "trade":
                    self._insert_trade_disk(disk_conn, record)
                    flushed += 1
                elif record_type == "calibration":
                    self._insert_calibration_disk(disk_conn, record)
                    flushed += 1
                elif record_type == "event":
                    self._insert_event_disk(disk_conn, record)
                    flushed += 1
            
            disk_conn.commit()
            
        except sqlite3.Error as e:
            disk_conn.rollback()
            self._error_count += 1
            logger.error(
                f"Erro no flush para disco: {e} | registros_afetados={flushed}"
            )
            # Tenta inserir um a um para recuperar o máximo possível
            flushed = self._fallback_single_inserts(records)
        
        return flushed
    
    def _fallback_single_inserts(self, records: List[Dict[str, Any]]) -> int:
        """Tentativa fallback de inserção individual em caso de erro no lote."""
        disk_conn = self._get_disk_connection()
        recovered = 0
        
        for record in records:
            try:
                disk_conn.execute("BEGIN IMMEDIATE TRANSACTION")
                record_type = record.get("_record_type", "telemetry")
                
                if record_type == "telemetry":
                    self._insert_telemetry_disk(disk_conn, record)
                elif record_type == "outcome":
                    self._insert_outcome_disk(disk_conn, record)
                elif record_type == "trade":
                    self._insert_trade_disk(disk_conn, record)
                elif record_type == "calibration":
                    self._insert_calibration_disk(disk_conn, record)
                elif record_type == "event":
                    self._insert_event_disk(disk_conn, record)
                
                disk_conn.commit()
                recovered += 1
                
            except sqlite3.Error:
                disk_conn.rollback()
                continue
        
        if recovered < len(records):
            logger.warning(
                f"Fallback recuperou {recovered}/{len(records)} registros"
            )
        
        return recovered
    
    def _insert_telemetry_disk(self, conn: sqlite3.Connection, r: Dict[str, Any]) -> None:
        """Insere registro de telemetria no disco."""
        conn.execute("""
            INSERT INTO logs_telemetria (
                timestamp, fixture_id, home_team, away_team, match_minute,
                score_home, score_away, corners_home, corners_away,
                dangerous_attacks_home, dangerous_attacks_away,
                xg_home, xg_away, pressure_home, pressure_away,
                corner_prob, signal_decision, edge, kelly_fraction,
                asian_corner_line, asian_corner_odds, odds_velocity,
                correlation_id, data_integrity, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("timestamp"),
            r.get("fixture_id"),
            r.get("home_team"),
            r.get("away_team"),
            r.get("match_minute"),
            r.get("score_home", 0),
            r.get("score_away", 0),
            r.get("corners_home", 0),
            r.get("corners_away", 0),
            r.get("dangerous_attacks_home", 0),
            r.get("dangerous_attacks_away", 0),
            r.get("xg_home", 0.0),
            r.get("xg_away", 0.0),
            r.get("pressure_home", 0.0),
            r.get("pressure_away", 0.0),
            r.get("corner_prob"),
            r.get("signal_decision"),
            r.get("edge"),
            r.get("kelly_fraction"),
            r.get("asian_corner_line"),
            r.get("asian_corner_odds"),
            r.get("odds_velocity"),
            r.get("correlation_id"),
            r.get("data_integrity"),
            json.dumps(r, default=str) if r.get("raw_payload") is None else r.get("raw_payload")
        ))
    
    def _insert_outcome_disk(self, conn: sqlite3.Connection, r: Dict[str, Any]) -> None:
        """Insere registro de outcome no disco."""
        conn.execute("""
            INSERT INTO signal_outcomes (
                fixture_id, signal_id, signal_decision, corner_prob,
                triggered_at, outcome, resolved_at, profit_loss, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("fixture_id"),
            r.get("signal_id"),
            r.get("signal_decision"),
            r.get("corner_prob"),
            r.get("triggered_at"),
            r.get("outcome"),
            r.get("resolved_at"),
            r.get("profit_loss", 0.0),
            r.get("correlation_id")
        ))
    
    def _insert_trade_disk(self, conn: sqlite3.Connection, r: Dict[str, Any]) -> None:
        """Insere registro de paper trade no disco."""
        conn.execute("""
            INSERT INTO paper_trades (
                fixture_id, trade_id, signal_decision, entry_time,
                entry_corner_line, entry_odds, stake, kelly_fraction,
                exit_time, exit_corner_line, exit_odds, outcome,
                profit_loss, risk_reason_code, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("fixture_id"),
            r.get("trade_id"),
            r.get("signal_decision"),
            r.get("entry_time"),
            r.get("entry_corner_line"),
            r.get("entry_odds"),
            r.get("stake"),
            r.get("kelly_fraction"),
            r.get("exit_time"),
            r.get("exit_corner_line"),
            r.get("exit_odds"),
            r.get("outcome"),
            r.get("profit_loss", 0.0),
            r.get("risk_reason_code"),
            r.get("correlation_id")
        ))
    
    def _insert_calibration_disk(self, conn: sqlite3.Connection, r: Dict[str, Any]) -> None:
        """Insere registro de calibração de risco no disco."""
        conn.execute("""
            INSERT INTO risk_calibration (
                calibration_date, parameter_name, old_value, new_value,
                reason, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            r.get("calibration_date"),
            r.get("parameter_name"),
            r.get("old_value"),
            r.get("new_value"),
            r.get("reason"),
            r.get("correlation_id")
        ))
    
    def _insert_event_disk(self, conn: sqlite3.Connection, r: Dict[str, Any]) -> None:
        """Insere registro de evento de sistema no disco."""
        conn.execute("""
            INSERT INTO system_events (
                event_type, event_level, message, details, correlation_id
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            r.get("event_type"),
            r.get("event_level", "INFO"),
            r.get("message"),
            r.get("details"),
            r.get("correlation_id")
        ))
    
    # ========== API Pública de Escrita ==========
    
    def log_telemetry(self, record: Dict[str, Any]) -> str:
        """
        Registra telemetria no buffer (RAM) sem I/O de disco.
        Retorna o correlation_id gerado ou existente.
        """
        correlation_id = record.get("correlation_id")
        if not correlation_id:
            correlation_id = f"tel_{int(time.time() * 1000)}_{id(record) % 100000:05d}"
            record["correlation_id"] = correlation_id
        
        record["_record_type"] = "telemetry"
        if "timestamp" not in record:
            record["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with self._lock:
            self._active_buffer.push(record)
            self._total_records_inserted += 1
        
        # Também insere no banco RAM para consultas imediatas
        self._insert_telemetry_ram(record)
        
        return correlation_id
    
    def _insert_telemetry_ram(self, r: Dict[str, Any]) -> None:
        """Insere telemetria no banco RAM para consultas instantâneas."""
        try:
            self._ram_conn.execute("""
                INSERT INTO logs_telemetria (
                    timestamp, fixture_id, home_team, away_team, match_minute,
                    score_home, score_away, corners_home, corners_away,
                    dangerous_attacks_home, dangerous_attacks_away,
                    xg_home, xg_away, pressure_home, pressure_away,
                    corner_prob, signal_decision, edge, kelly_fraction,
                    asian_corner_line, asian_corner_odds, odds_velocity,
                    correlation_id, data_integrity, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get("timestamp"),
                r.get("fixture_id"),
                r.get("home_team"),
                r.get("away_team"),
                r.get("match_minute"),
                r.get("score_home", 0),
                r.get("score_away", 0),
                r.get("corners_home", 0),
                r.get("corners_away", 0),
                r.get("dangerous_attacks_home", 0),
                r.get("dangerous_attacks_away", 0),
                r.get("xg_home", 0.0),
                r.get("xg_away", 0.0),
                r.get("pressure_home", 0.0),
                r.get("pressure_away", 0.0),
                r.get("corner_prob"),
                r.get("signal_decision"),
                r.get("edge"),
                r.get("kelly_fraction"),
                r.get("asian_corner_line"),
                r.get("asian_corner_odds"),
                r.get("odds_velocity"),
                r.get("correlation_id"),
                r.get("data_integrity"),
                json.dumps(r, default=str) if r.get("raw_payload") is None else r.get("raw_payload")
            ))
        except sqlite3.Error as e:
            logger.error(f"Erro ao inserir telemetria no RAM: {e}")
    
    def log_signal(self, fixture_id: str, signal_id: str, signal_decision: str,
                   corner_prob: Optional[float] = None,
                   asian_corner_line: Optional[float] = None,
                   asian_corner_odds: Optional[float] = None,
                   odds_velocity: Optional[float] = None,
                   correlation_id: Optional[str] = None) -> str:
        """Registra sinal gerado."""
        if not correlation_id:
            correlation_id = f"sig_{int(time.time() * 1000)}_{id(fixture_id) % 100000:05d}"
        
        record = {
            "_record_type": "outcome",
            "fixture_id": fixture_id,
            "signal_id": signal_id,
            "signal_decision": signal_decision,
            "corner_prob": corner_prob,
            "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "correlation_id": correlation_id,
            "asian_corner_line": asian_corner_line,
            "asian_corner_odds": asian_corner_odds,
            "odds_velocity": odds_velocity
        }
        
        with self._lock:
            self._active_buffer.push(record)
            self._total_records_inserted += 1
        
        return correlation_id
    
    def log_paper_trade(self, fixture_id: str, trade_id: str, signal_decision: str,
                        stake: float, kelly_fraction: Optional[float] = None,
                        entry_corner_line: Optional[float] = None,
                        entry_odds: Optional[float] = None,
                        risk_reason_code: Optional[str] = None,
                        correlation_id: Optional[str] = None) -> str:
        """Registra abertura de paper trade."""
        if not correlation_id:
            correlation_id = f"trd_{int(time.time() * 1000)}_{id(trade_id) % 100000:05d}"
        
        record = {
            "_record_type": "trade",
            "fixture_id": fixture_id,
            "trade_id": trade_id,
            "signal_decision": signal_decision,
            "entry_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "entry_corner_line": entry_corner_line,
            "entry_odds": entry_odds,
            "stake": stake,
            "kelly_fraction": kelly_fraction,
            "risk_reason_code": risk_reason_code,
            "correlation_id": correlation_id
        }
        
        with self._lock:
            self._active_buffer.push(record)
            self._total_records_inserted += 1
        
        return correlation_id
    
    def close_paper_trade(self, trade_id: str, outcome: str,
                          exit_corner_line: Optional[float] = None,
                          exit_odds: Optional[float] = None,
                          profit_loss: float = 0.0) -> bool:
        """Fecha paper trade existente."""
        disk_conn = self._get_disk_connection()
        try:
            disk_conn.execute("""
                UPDATE paper_trades 
                SET exit_time = ?, exit_corner_line = ?, exit_odds = ?,
                    outcome = ?, profit_loss = ?
                WHERE trade_id = ? AND outcome IS NULL
            """, (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                exit_corner_line,
                exit_odds,
                outcome,
                profit_loss,
                trade_id
            ))
            disk_conn.commit()
            return disk_conn.total_changes > 0
        except sqlite3.Error as e:
            logger.error(f"Erro ao fechar paper trade {trade_id}: {e}")
            return False
    
    def log_risk_calibration(self, parameter_name: str, old_value: Optional[float],
                             new_value: Optional[float], reason: Optional[str] = None,
                             correlation_id: Optional[str] = None) -> str:
        """Registra calibração de parâmetro de risco."""
        if not correlation_id:
            correlation_id = f"cal_{int(time.time() * 1000)}_{id(parameter_name) % 100000:05d}"
        
        record = {
            "_record_type": "calibration",
            "calibration_date": time.strftime("%Y-%m-%d"),
            "parameter_name": parameter_name,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "correlation_id": correlation_id
        }
        
        with self._lock:
            self._active_buffer.push(record)
            self._total_records_inserted += 1
        
        return correlation_id
    
    def log_system_event(self, event_type: str, message: Optional[str] = None,
                         event_level: str = "INFO", details: Optional[str] = None,
                         correlation_id: Optional[str] = None) -> str:
        """Registra evento de sistema para observabilidade."""
        if not correlation_id:
            correlation_id = f"evt_{int(time.time() * 1000)}_{id(event_type) % 100000:05d}"
        
        record = {
            "_record_type": "event",
            "event_type": event_type,
            "event_level": event_level,
            "message": message,
            "details": details,
            "correlation_id": correlation_id
        }
        
        with self._lock:
            self._active_buffer.push(record)
            self._total_records_inserted += 1
        
        return correlation_id
    
    # ========== API Pública de Consulta ==========
    
    def get_telemetry_by_fixture(self, fixture_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Consulta telemetria de uma partida do banco RAM."""
        try:
            cursor = self._ram_conn.execute("""
                SELECT * FROM logs_telemetria 
                WHERE fixture_id = ? 
                ORDER BY id DESC 
                LIMIT ?
            """, (fixture_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Erro na consulta de telemetria: {e}")
            return []
    
    def get_latest_telemetry(self, fixture_id: str) -> Optional[Dict[str, Any]]:
        """Retorna a telemetria mais recente de uma partida."""
        results = self.get_telemetry_by_fixture(fixture_id, limit=1)
        return results[0] if results else None
    
    def get_open_trades(self, fixture_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna paper trades abertos."""
        disk_conn = self._get_disk_connection()
        try:
            if fixture_id:
                cursor = disk_conn.execute("""
                    SELECT * FROM paper_trades 
                    WHERE outcome IS NULL AND fixture_id = ?
                    ORDER BY entry_time DESC
                """, (fixture_id,))
            else:
                cursor = disk_conn.execute("""
                    SELECT * FROM paper_trades 
                    WHERE outcome IS NULL
                    ORDER BY entry_time DESC
                """)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Erro ao consultar trades abertos: {e}")
            return []
    
    def get_pending_outcomes(self, fixture_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna sinais com outcome pendente."""
        disk_conn = self._get_disk_connection()
        try:
            if fixture_id:
                cursor = disk_conn.execute("""
                    SELECT * FROM signal_outcomes 
                    WHERE outcome IS NULL AND fixture_id = ?
                    ORDER BY triggered_at DESC
                """, (fixture_id,))
            else:
                cursor = disk_conn.execute("""
                    SELECT * FROM signal_outcomes 
                    WHERE outcome IS NULL
                    ORDER BY triggered_at DESC
                """)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Erro ao consultar outcomes pendentes: {e}")
            return []
    
    def get_system_events(self, event_type: Optional[str] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """Consulta eventos de sistema."""
        disk_conn = self._get_disk_connection()
        try:
            if event_type:
                cursor = disk_conn.execute("""
                    SELECT * FROM system_events 
                    WHERE event_type = ?
                    ORDER BY id DESC 
                    LIMIT ?
                """, (event_type, limit))
            else:
                cursor = disk_conn.execute("""
                    SELECT * FROM system_events 
                    ORDER BY id DESC 
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Erro ao consultar eventos: {e}")
            return []
    
    # ========== Estatísticas e Monitoramento ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas operacionais do store."""
        with self._lock:
            buffer_count = self._active_buffer.count
        
        time_since_flush = time.time() - self._last_flush_time if self._last_flush_time else -1
        
        return {
            "buffer_count": buffer_count,
            "buffer_capacity": self._buffer_size,
            "buffer_utilization_pct": (buffer_count / self._buffer_size) * 100 if self._buffer_size else 0,
            "total_inserted": self._total_records_inserted,
            "total_flushed": self._total_records_flushed,
            "flush_count": self._flush_count,
            "error_count": self._error_count,
            "time_since_flush_ms": int(time_since_flush * 1000) if time_since_flush >= 0 else -1,
            "disk_db_path": self._db_disk_path,
            "disk_connected": self._disk_conn is not None,
            "schema_version": self.SCHEMA_VERSION
        }
    
    def force_flush_sync(self) -> int:
        """Força flush síncrono (para shutdown ou testes)."""
        return self._force_flush()


# Instância singleton global
_store_instance: Optional[HybridDataStore] = None
_store_lock = threading.Lock()


def get_hybrid_store(db_path: Optional[str] = None) -> HybridDataStore:
    """
    Retorna instância singleton do HybridDataStore.
    Inicializa automaticamente no primeiro acesso.
    """
    global _store_instance
    
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                if db_path is None:
                    # Caminho padrão baseado no diretório do engine
                    engine_dir = os.path.dirname(os.path.abspath(__file__))
                    db_path = os.path.join(engine_dir, "aura_quant_x.db")
                
                _store_instance = HybridDataStore(db_path)
                _store_instance.start()
    
    return _store_instance


def shutdown_hybrid_store() -> None:
    """Finaliza o store híbrido de forma limpa."""
    global _store_instance
    
    with _store_lock:
        if _store_instance is not None:
            _store_instance.stop(wait_flush=True)
            _store_instance = None
