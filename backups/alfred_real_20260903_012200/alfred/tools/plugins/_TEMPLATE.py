# Modelo de ferramenta. Este ficheiro NÃO é carregado (começa por _).
# Copia, preenche, envia no chat: Alfred, instala esta ferramenta
# ```python
# ...este contrato...
# ```

TOOL_NAME = "echo_note"
RISK = "low"
MUTATING = False
SUMMARY = "Devolve o texto recebido. Exemplo de plugin seguro."

from alfred.validators import ValidationError


def validate(args):
    args = args or {}
    text = str(args.get("text") or "").strip()
    if not text:
        raise ValidationError("text vazio")
    if len(text) > 500:
        raise ValidationError("text excede 500 caracteres")
    return {"text": text}


def run(args, ctx):
    a = validate(args)
    return {"echo": a["text"], "job_id": getattr(ctx, "job_id", "")}
