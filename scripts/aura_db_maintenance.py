#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Database Maintenance v1.0
Otimização, vacuum, índices e verificação de integridade para SQLite.
"""
import os, sys, sqlite3, time
from pathlib import Path

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
DB_PATH = AURA_ROOT / "engine" / "aura_quant_x.db"
LOG_PATH = AURA_ROOT / "logs_supervisor" / "db_maintenance.log"


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def optimize_pragmas(conn: sqlite3.Connection):
    """Aplica PRAGMAs de performance."""
    pragmas = [
        ("PRAGMA journal_mode=WAL", "WAL mode"),
        ("PRAGMA synchronous=NORMAL", "synchronous NORMAL"),
        ("PRAGMA cache_size=-64000", "cache 64MB"),
        ("PRAGMA temp_store=MEMORY", "temp memory"),
        ("PRAGMA mmap_size=268435456", "mmap 256MB"),
        ("PRAGMA foreign_keys=ON", "foreign keys"),
        ("PRAGMA auto_vacuum=INCREMENTAL", "auto vacuum incremental"),
    ]
    for sql, desc in pragmas:
        try:
            conn.execute(sql)
            log(f"  [OK] {desc}")
        except Exception as e:
            log(f"  [ERRO] {desc}: {e}")


def create_indexes(conn: sqlite3.Connection):
    """Cria índices essenciais se não existirem."""
    indexes = [
        ("idx_captures_fixture_time", "CREATE INDEX IF NOT EXISTS idx_captures_fixture_time ON captures(fixture_id, captured_at)"),
        ("idx_tips_created", "CREATE INDEX IF NOT EXISTS idx_tips_created ON tips(created_at DESC)"),
        ("idx_feedback_agent", "CREATE INDEX IF NOT EXISTS idx_feedback_agent ON feedback(agent_id, created_at)"),
        ("idx_health_checks", "CREATE INDEX IF NOT EXISTS idx_health_checks ON health_checks(service, checked_at DESC)"),
    ]
    for name, sql in indexes:
        try:
            conn.execute(sql)
            log(f"  [OK] Índice {name} criado/verificado")
        except Exception as e:
            log(f"  [ERRO] Índice {name}: {e}")


def vacuum_and_analyze(conn: sqlite3.Connection):
    """Executa VACUUM e ANALYZE."""
    try:
        log("  [INFO] Executando VACUUM (pode demorar)...")
        conn.execute("VACUUM")
        log("  [OK] VACUUM concluído")
    except Exception as e:
        log(f"  [ERRO] VACUUM: {e}")

    try:
        log("  [INFO] Executando ANALYZE...")
        conn.execute("ANALYZE")
        log("  [OK] ANALYZE concluído")
    except Exception as e:
        log(f"  [ERRO] ANALYZE: {e}")


def check_integrity(conn: sqlite3.Connection) -> dict:
    """Verifica integridade do banco."""
    try:
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        return {"ok": result == "ok", "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Coleta estatísticas do banco."""
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        stats = {}
        for table in tables:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            stats[table] = count

        # Tamanho do arquivo
        db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

        return {"tables": stats, "total_tables": len(tables), "db_size_mb": round(db_size / (1024*1024), 2)}
    except Exception as e:
        return {"error": str(e)}


def main():
    log("=" * 60)
    log("AURA Database Maintenance v1.0")
    log(f"DB: {DB_PATH}")
    log("=" * 60)

    if not DB_PATH.exists():
        log("[AVISO] Banco de dados não encontrado. Pulando manutenção.")
        return 0

    conn = sqlite3.connect(str(DB_PATH), timeout=30)

    # 1. Otimizar PRAGMAs
    log("[1/4] Otimizando PRAGMAs...")
    optimize_pragmas(conn)

    # 2. Criar índices
    log("[2/4] Criando/verificando índices...")
    create_indexes(conn)

    # 3. Integridade
    log("[3/4] Verificando integridade...")
    integrity = check_integrity(conn)
    log(f"  [{'OK' if integrity['ok'] else 'FALHA'}] Integridade: {integrity.get('result', integrity.get('error'))}")

    # 4. Vacuum e analyze
    log("[4/4] Vacuum e analyze...")
    vacuum_and_analyze(conn)

    # Estatísticas
    stats = get_db_stats(conn)
    log(f"[STATS] {stats}")

    conn.close()

    log("=" * 60)
    log("Manutenção concluída")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
