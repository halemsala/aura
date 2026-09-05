TOOL_NAME = "echo_note"
RISK = "low"
MUTATING = False
SUMMARY = "eco seguro"

from alfred.validators import ValidationError

def validate(args):
    text = str((args or {}).get("text") or "").strip()
    if not text:
        raise ValidationError("text vazio")
    return {"text": text[:200]}

def run(args, ctx):
    a = validate(args)
    return {"echo": a["text"]}