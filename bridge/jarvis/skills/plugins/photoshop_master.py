# bridge/jarvis/skills/plugins/photoshop_master.py
"""
Skill: Photoshop Master (Creative Edition)
Controle nativo do Adobe Photoshop via API COM.
Requer: pip install photoshop-python-api (ou equivalente) e Photoshop instalado.
"""
import logging
import os
from typing import Dict

logger = logging.getLogger("aura.skill.photoshop")

try:
    from bridge.jarvis.memory.project_memory import PROJECT_MEMORY
except Exception:
    PROJECT_MEMORY = None


class Skill:
    def __init__(self):
        self.description = (
            "Cria projetos no Photoshop. Acoes: new_project, import_asset, "
            "apply_artistic_filter, add_text_layer, save_current_style, apply_remembered_style."
        )
        self.app = None
        self._connect()

    def _connect(self):
        try:
            import photoshop as ps
            self.app = ps.Application()
            logger.info("Conectado ao Adobe Photoshop.")
        except Exception as e:
            logger.error("Photoshop nao encontrado: %s", e)
            self.app = None

    def run(self, action: str, args: Dict) -> str:
        if not self.app:
            return "Photoshop nao esta disponivel."
        try:
            import photoshop as ps

            if action == "new_project":
                doc_name = args.get("name", "AURA_Project")
                width = args.get("width", 1920)
                height = args.get("height", 1080)
                self.app.documents.add(width, height, 72, doc_name)
                return f"Novo projeto criado: {doc_name} ({width}x{height})."

            elif action == "import_asset":
                asset_path = args.get("path", "").replace("\\", "\\\\")
                if os.path.exists(asset_path):
                    self.app.open(asset_path)
                    return f"Imagem importada: {asset_path}."
                return f"Arquivo nao encontrado: {asset_path}."

            elif action == "apply_artistic_filter":
                filter_type = args.get("filter", "oil_paint")
                layer = self.app.activeDocument.activeLayer
                if filter_type == "oil_paint":
                    layer.applyOilPaint()
                    return "Filtro Pintura a Oleo aplicado a camada ativa."
                elif filter_type == "gaussian_blur":
                    radius = args.get("radius", 5)
                    layer.applyGaussianBlur(radius)
                    return f"Desfoque Gaussiano aplicado (Raio: {radius})."

            elif action == "add_text_layer":
                text = args.get("text", "Texto Padrao")
                size = args.get("size", 72)
                new_layer = self.app.activeDocument.artLayers.add()
                new_layer.kind = ps.LayerKind.TextLayer
                new_layer.textItem.contents = text
                new_layer.textItem.size = size
                return f"Camada de texto adicionada: '{text}'."

            elif action == "save_current_style":
                if PROJECT_MEMORY is None:
                    return "ProjectMemory indisponivel."
                project_name = args.get("name", "Unnamed_Project")
                fonts = args.get("fonts", ["Arial"])
                colors = args.get("colors", ["#000000", "#FFFFFF"])
                dims = args.get("dims", "1920x1080")
                filters = args.get("filters", [])
                PROJECT_MEMORY.save_project_style(project_name, fonts, colors, dims, filters)
                return f"Estilo do projeto '{project_name}' memorizado com sucesso."

            elif action == "apply_remembered_style":
                if PROJECT_MEMORY is None:
                    return "ProjectMemory indisponivel."
                project_name = args.get("name", "")
                style = PROJECT_MEMORY.recall_project_style(project_name)
                if not style:
                    return f"Nao lembro de nenhum projeto chamado '{project_name}'."
                return (
                    f"Reaplicando estilo de '{project_name}': "
                    f"Fontes {style['fonts']}, Cores {style['colors']}."
                )

            return "Acao do Photoshop nao reconhecida."
        except Exception as e:
            logger.error("Erro no Photoshop Master: %s", e)
            return f"Erro ao executar no Photoshop: {e}"
