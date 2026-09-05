# bridge/jarvis/governor/jarvis_telegram_dualmode.py
"""
JARVIS Telegram Dual-Mode - Pronto para uso
-------------------------------------------
Já vem com os botões de Modo Assistente / Modo Trading configurados.

Como usar:
1. Coloque este arquivo em: C:\aura\bridge\jarvis\governor\
2. No seu bot principal, importe e inicie assim:

    from bridge.jarvis.governor.jarvis_telegram_dualmode import start_dualmode_bot
    start_dualmode_bot("SEU_TOKEN_AQUI", chat_id_permitido=SEU_CHAT_ID)

Ou rode direto:
    python -m bridge.jarvis.governor.jarvis_telegram_dualmode
"""

from __future__ import annotations
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Importa o Governor (Dual-Mode)
try:
    from bridge.jarvis.governor.resource_governor import GOVERNOR
except ImportError:
    # Fallback caso rode fora do path do AURA
    import sys
    sys.path.insert(0, r"C:\aura")
    from bridge.jarvis.governor.resource_governor import GOVERNOR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aura.telegram.dualmode")

# ====================== CONFIGURAÇÃO ======================
# Coloque seu token e chat_id aqui (ou use variáveis de ambiente)
BOT_TOKEN = "8901552625:AAEw0CgOZByKImi_aGZWXHMaSedd3hRYZ38"  # Novo token
ALLOWED_CHAT_ID = 7947886756  # Novo chat ID
# ==========================================================


def get_mode_keyboard():
    """Teclado inline com os botões de modo."""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Modo Assistente", callback_data="mode_assistant"),
            InlineKeyboardButton("🔴 Modo Trading", callback_data="mode_trading"),
        ],
        [
            InlineKeyboardButton("📊 Status Atual", callback_data="mode_status"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_keyboard():
    """Teclado principal (sempre visível)."""
    keyboard = [
        ["🟢 Modo Assistente", "🔴 Modo Trading"],
        ["📊 Status", "❓ Ajuda"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("Acesso negado.")
        return

    await update.message.reply_text(
        "🤖 *JARVIS Dual-Mode*\n\n"
        "Escolha o modo de operação:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    await update.message.reply_text(
        "Ou use os botões abaixo:",
        reply_markup=get_mode_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    text = (
        "*Comandos disponíveis:*\n\n"
        "🟢 *Modo Assistente* → Desliga o AURA e libera recursos\n"
        "🔴 *Modo Trading* → Desliga o Assistente e sobe o AURA\n"
        "📊 *Status* → Mostra o modo atual\n\n"
        "Você também pode digitar:\n"
        "`modo assistente` ou `modo trading`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de texto."""
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    text = (update.message.text or "").lower().strip()

    if "modo assistente" in text or text == "🟢 modo assistente":
        result = GOVERNOR.switch_to_assistant_mode()
        await update.message.reply_text(f"✅ {result}", reply_markup=get_mode_keyboard())

    elif "modo trading" in text or text == "🔴 modo trading":
        result = GOVERNOR.switch_to_trading_mode()
        await update.message.reply_text(f"✅ {result}", reply_markup=get_mode_keyboard())

    elif "status" in text or text == "📊 status":
        status = GOVERNOR.get_status()
        await update.message.reply_text(f"📊 {status}", reply_markup=get_mode_keyboard())

    elif "ajuda" in text or "help" in text:
        await help_command(update, context)

    else:
        await update.message.reply_text(
            "Não entendi. Use os botões ou digite:\n"
            "• modo assistente\n"
            "• modo trading\n"
            "• status",
            reply_markup=get_main_keyboard()
        )


async def mode_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques nos botões inline."""
    query = update.callback_query
    await query.answer()

    if ALLOWED_CHAT_ID and query.message.chat_id != ALLOWED_CHAT_ID:
        await query.edit_message_text("Acesso negado.")
        return

    data = query.data

    if data == "mode_assistant":
        result = GOVERNOR.switch_to_assistant_mode()
        await query.edit_message_text(f"✅ {result}")

    elif data == "mode_trading":
        result = GOVERNOR.switch_to_trading_mode()
        await query.edit_message_text(f"✅ {result}")

    elif data == "mode_status":
        status = GOVERNOR.get_status()
        await query.edit_message_text(f"📊 {status}", reply_markup=get_mode_keyboard())


def start_dualmode_bot(token: str = None, chat_id: int = None):
    """Inicia o bot Dual-Mode."""
    global BOT_TOKEN, ALLOWED_CHAT_ID

    if token:
        BOT_TOKEN = token
    if chat_id:
        ALLOWED_CHAT_ID = chat_id

    if not BOT_TOKEN:
        print("❌ ERRO: Configure o BOT_TOKEN antes de iniciar.")
        print("   Edite o arquivo ou passe o token: start_dualmode_bot('seu_token')")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(mode_button_callback, pattern="^mode_"))

    print("✅ JARVIS Dual-Mode Bot iniciado.")
    print(f"   Chat permitido: {ALLOWED_CHAT_ID or 'qualquer'}")
    app.run_polling()


if __name__ == "__main__":
    # Para rodar direto: python jarvis_telegram_dualmode.py
    start_dualmode_bot()
