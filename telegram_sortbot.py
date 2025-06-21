import os
import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

def extract_ids(text):
    ids = set()
    for line in text.splitlines():
        match = re.search(r"\b(\d{5})\b", line)
        if match:
            ids.add(match.group(1))
    return ids

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load BOT TOKEN securely ---
BOT_TOKEN = os.getenv("7809326409:AAHMOWhaZx0vEF_d-AmA3Hmmr7G89zOsrNA")

# ---------- Utility Functions ----------

def extract_name_only(line):
    cleaned = re.sub(r'💎|🍬|\(.*?\)', '', line)
    cleaned = re.sub(r'^\s*\d+\.\s*', '', cleaned)
    cleaned = re.sub(r'^\s*', '', cleaned)
    return cleaned.strip().lower()

def clean_display_line(line):
    line = re.sub(r'💎|🍬|\(.*?\)', '', line)
    return line.strip()

def extract_sorted_numbers(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    numbers = []
    for line in lines:
        match = re.search(r'(\d+)', line)
        if match:
            numbers.append(int(match.group(1)))
    sorted_numbers = sorted(numbers)
    return ' '.join(str(num) for num in sorted_numbers) if sorted_numbers else "Nenhum número encontrado para ordenar."

def filter_multiple_units(text):
    lines = text.split('\n')
    filtered = [
        line for line in lines
        if re.search(r'\((\d+)x\)', line) and int(re.search(r'\((\d+)x\)', line).group(1)) > 1
    ]
    return '\n'.join(filtered) if filtered else "Nenhum item com mais de 1 unidade encontrado."

def expand_ids_from_text(text):
    results = []

    for line in text.strip().splitlines():
        match = re.search(r"\b(\d{5})\b", line)
        if not match:
            continue

        code = match.group(1)

        # Check for quantity like (4x)
        qty_match = re.search(r"\((\d+)x\)", line)
        qty = int(qty_match.group(1)) if qty_match else 1

        results.extend([code] * qty)

    return " ".join(results)

# ---------- UI ----------

def get_main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💎 Ordenar Números", callback_data="mode_sort"),
            InlineKeyboardButton("📋 Comparar Listas", callback_data="mode_compare"),
        ],
        [
            InlineKeyboardButton("🗑️ Remover 1x", callback_data="mode_filter"),
        ]
    ])

def get_back_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Voltar ao menu", callback_data="main_menu")]
    ])

async def send_image_with_caption(file_name, caption, message, keyboard=None):
    try:
        with open(file_name, "rb") as img:
            await message.reply_photo(photo=InputFile(img), caption=caption, reply_markup=keyboard)
    except Exception as e:
        await message.reply_text("⚠️ Não consegui carregar a imagem.")
        logger.error(f"[ERRO IMG] {file_name}: {e}")

# ---------- Commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_image_with_caption("menu_banner.jpg", "Escolha o que você quer fazer:", update.message, get_main_menu())

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_image_with_caption("menu_banner.jpg", "Menu de opções:", update.message, get_main_menu())

async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode, banner_file, caption_text):
    context.user_data["mode"] = mode
    context.user_data["pending_list"] = []
    await send_image_with_caption(banner_file, caption_text + "\n\n🔽 Quando quiser mudar, clique abaixo:", update.message, get_back_button())

async def set_sort_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, "mode_sort", "banner_sort.jpg", "Modo definido: 💎 Ordenar Números.\nEnvie a lista com 💎.")

async def set_compare_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, "mode_compare", "banner_compare.jpg", "Modo definido: 📋 Comparar Listas.\nEnvie duas listas em mensagens separadas.")

async def set_filter_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_mode(update, context, "mode_filter", "banner_filter.jpg", "Modo definido: 🗑️ Remover 1x.\nEnvie os cards para filtrar.")

async def expand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "mode_expand"
    await update.message.reply_text("✅ Modo Expandir ativado. Envie a lista com quantidades agora.")

# ---------- Button Handler ----------

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode_map = {
        "mode_sort": ("mode_sort", "banner_sort.jpg", "Modo definido: 💎 Ordenar Números.\nEnvie a lista com 💎."),
        "mode_compare": ("mode_compare", "banner_compare.jpg", "Modo definido: 📋 Comparar Listas.\nEnvie duas listas em mensagens separadas."),
        "mode_filter": ("mode_filter", "banner_filter.jpg", "Modo definido: 🗑️ Remover 1x.\nEnvie os cards para filtrar.")
    }

    if query.data == "main_menu":
        await send_image_with_caption("menu_banner.jpg", "Escolha o que você quer fazer:", query.message, get_main_menu())
        context.user_data.clear()
        return

    if query.data in mode_map:
        mode, banner, text = mode_map[query.data]
        context.user_data["mode"] = mode
        context.user_data["pending_list"] = []
        await send_image_with_caption(banner, text + "\n\n🔽 Quando quiser mudar:", query.message, get_back_button())

# ---------- Compare Handler ----------

def compare_lists_pairwise(list1_raw, list2_raw):
    list1_lines = [line.strip() for line in list1_raw.strip().split('\n') if line.strip()]
    list2_lines = [line.strip() for line in list2_raw.strip().split('\n') if line.strip()]

    # Build maps from ID to line
    list1_map = {}
    list2_map = {}

    for line in list1_lines:
        match = re.search(r'\b(\d{5})\b', line)
        if match:
            list1_map[match.group(1)] = line.strip()

    for line in list2_lines:
        match = re.search(r'\b(\d{5})\b', line)
        if match:
            list2_map[match.group(1)] = line.strip()

    # Find common IDs
    common_ids = sorted(set(list1_map.keys()) & set(list2_map.keys()))

    # Return matching lines from list1
    results = [list1_map[id] for id in common_ids]
    return results if results else None

# ---------- Message Handler ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    if not mode:
        await update.message.reply_text("Por favor, use /start ou /menu para escolher uma opção.")
        return

    if mode == "mode_sort":
        result = extract_sorted_numbers(text)    

    elif mode == "mode_filter":
        result = filter_multiple_units(text)

    elif mode == "mode_compare":
        pending = context.user_data.get("pending_list", [])
        pending.append(text)
        context.user_data["pending_list"] = pending

    if len(pending) < 2:
        await update.message.reply_text("✅ Lista 1 recebida. Agora envie a segunda lista.")
        return
    else:
        matches = compare_lists_pairwise(pending[0], pending[1])
        result = "📋 Itens em comum:\n" + '\n'.join(matches) if matches else "Nenhum item em comum encontrado."
        context.user_data["pending_list"] = []

    elif mode == "mode_expand":
        result = expand_ids_from_text(text)

else:
    result = "⚠️ Modo desconhecido. Tente /start novamente."

    await update.message.reply_text(result)
    await update.message.reply_text("🔽 Quando quiser mudar:", reply_markup=get_back_button())

# ---------- Bot Setup ----------

if __name__ == "__main__":
    app = ApplicationBuilder()\
        .token("7809326409:AAHMOWhaZx0vEF_d-AmA3Hmmr7G89zOsrNA")\
        .read_timeout(30)\
        .write_timeout(30)\
        .connect_timeout(30)\
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("ordenar", set_sort_mode))
    app.add_handler(CommandHandler("comparar", set_compare_mode))
    app.add_handler(CommandHandler("remover", set_filter_mode))
    app.add_handler(CommandHandler("expand", expand))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    app.run_polling()
    
    