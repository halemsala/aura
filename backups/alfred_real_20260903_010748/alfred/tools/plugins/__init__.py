# Plugins de ferramentas. Ficheiros _*.py não são carregados.
# Contrato mínimo (rever → instalar → rever):
#   TOOL_NAME = "nome_snake"
#   RISK = "low" | "medium" | "high"
#   MUTATING = True
#   SUMMARY = "..."
#   def validate(args): ...
#   def run(args, ctx): ...
# Imports permitidos: json/re/time/pathlib/typing + alfred.validators (resolve_allowed).
