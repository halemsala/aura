# bridge/jarvis/skills/skill_manager.py
"""
Skill Manager v1.0
Carrega habilidades dinamicamente e executa acoes do sistema.

SKILLS_ENABLED = False por padrao. Ative sob supervisao.
Override por ambiente: AURA_SKILLS_ENABLED=1 (ou true/yes/on).
"""
import importlib
import logging
import json
import os
from pathlib import Path

logger = logging.getLogger("aura.skills")

def _env_flag(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default

# OPT-IN: False por defeito; AURA_ATIVAR_ASSISTENTE_WINDOWS.bat define AURA_SKILLS_ENABLED=1
SKILLS_ENABLED = _env_flag("AURA_SKILLS_ENABLED", default=False)


class SkillManager:
    def __init__(self, skills_dir: str = "bridge/jarvis/skills/plugins"):
        self.skills_dir = Path(skills_dir)
        self.installed_skills = {}
        if SKILLS_ENABLED:
            self._discover_skills()
        else:
            logger.info("SkillManager: SKILLS_ENABLED=False (nenhuma skill carregada).")

    def _discover_skills(self):
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        for skill_file in self.skills_dir.glob("*.py"):
            if skill_file.stem.startswith("_"):
                continue
            module_name = f"jarvis.skills.plugins.{skill_file.stem}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "Skill"):
                    skill_instance = module.Skill()
                    self.installed_skills[skill_file.stem] = skill_instance
                    logger.info("Skill carregada: %s", skill_file.stem)
            except Exception as e:
                logger.error("Falha ao carregar skill %s: %s", skill_file.stem, e)

    def get_skill_prompt(self) -> str:
        if not self.installed_skills:
            return "Voce nao tem habilidades instaladas (ou SKILLS_ENABLED=False)."
        prompts = ["Voce tem acesso as seguintes habilidades:\n"]
        for name, skill in self.installed_skills.items():
            prompts.append(f"- Skill: {name} | Descricao: {skill.description}")
        return "\n".join(prompts)

    def execute_skill(self, skill_name: str, action: str, args: dict) -> str:
        if not SKILLS_ENABLED:
            return "SKILLS_ENABLED=False. Execucao bloqueada."
        skill = self.installed_skills.get(skill_name)
        if not skill:
            return f"Skill '{skill_name}' nao encontrada."
        try:
            logger.info("Executando skill %s.%s com args: %s", skill_name, action, args)
            result = skill.run(action, args)
            self._learn_from_execution(skill_name, action, args, result)
            return result
        except Exception as e:
            return f"Erro ao executar skill: {e}"

    def _learn_from_execution(self, skill, action, args, result):
        log_file = Path("engine/data/jarvis_experience.jsonl")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "skill": skill,
                        "action": action,
                        "args": args,
                        "success": "Erro" not in str(result),
                    }
                )
                + "\n"
            )


SKILL_MANAGER = SkillManager()
