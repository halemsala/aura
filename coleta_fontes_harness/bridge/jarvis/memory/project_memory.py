# bridge/jarvis/memory/project_memory.py
"""
Project Memory Manager v1.0
Salva e recupera metadados de projetos no SQLite (CPU).
"""
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aura.memory.projects")
DB_PATH = Path("engine/data/jarvis_memory.db")


class ProjectMemoryManager:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS creative_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT UNIQUE,
                    style_tags TEXT,
                    fonts_used TEXT,
                    color_palette TEXT,
                    dimensions TEXT,
                    filters_applied TEXT,
                    created_at TEXT
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Erro ao inicializar DB de Memoria: %s", e)

    def save_project_style(self, name: str, fonts: list, colors: list, dims: str, filters: list, tags: list = None):
        if tags is None:
            tags = []
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                """
                INSERT OR REPLACE INTO creative_projects
                (project_name, style_tags, fonts_used, color_palette, dimensions, filters_applied, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    json.dumps(tags),
                    json.dumps(fonts),
                    json.dumps(colors),
                    dims,
                    json.dumps(filters),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("Erro ao salvar projeto: %s", e)
            return False

    def recall_project_style(self, name: str) -> dict:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT * FROM creative_projects WHERE project_name = ?", (name,))
            row = c.fetchone()
            conn.close()
            if row:
                return {
                    "project_name": row[1],
                    "tags": json.loads(row[2]),
                    "fonts": json.loads(row[3]),
                    "colors": json.loads(row[4]),
                    "dimensions": row[5],
                    "filters": json.loads(row[6]),
                }
            return None
        except Exception as e:
            logger.error("Erro ao resgatar projeto: %s", e)
            return None


PROJECT_MEMORY = ProjectMemoryManager()
