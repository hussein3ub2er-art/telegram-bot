"""
بوت تلكرام مدعوم بذكاء Claude الاصطناعي (Anthropic)
--------------------------------------------------
المتطلبات: python-telegram-bot, anthropic, python-dotenv
"""

import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from anthropic import Anthropic

import db
import converters
from keep_alive import keep_alive

# تحميل متغيرات البيئة من ملف .env (إذا موجود)
load_dotenv()

# ==== ضع التوكن والمفتاح هنا مباشرة (بديل عن ملف .env) ====
# إذا حطيت القيم هنا، خله بينهم علامات تنصيص "" وما تمسحهم.
# إذا سويت ملف .env فهو بياخذ الأولوية تلقائياً.
TELEGRAM_TOKEN_MANUAL = "ضع_توكن_البوت_هنا"
ANTHROPIC_API_KEY_MANUAL = "ضع_مفتاح_Anthropic_هنا"
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_TOKEN_MANUAL
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY_MANUAL

# إعداد تسجيل الأحداث (logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# عميل Anthropic
client = Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_HISTORY_MESSAGES = 20  # لتفادي تضخم السياق (تُقرأ وتُحفظ في قاعدة البيانات)
SYSTEM_PROMPT = "أنت مساعد ذكي وودود تجاوب باللغة العربية بشكل واضح ومختصر."

TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /start"""
    await update.message.reply_text(
        "أهلاً! أنا بوت مدعوم بذكاء Claude الاصطناعي. أرسل لي أي رسالة وراح أجاوبك.\n"
        "سجل المحادثة يُحفظ بشكل دائم. استخدم /reset لمسحه.\n\n"
        "كمان أقدر أحوّل لك الملفات: أرسل PDF أو Word (.docx) أو PowerPoint (.pptx) "
        "وراح أحوّله لك."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /reset لمسح سجل المحادثة من قاعدة البيانات"""
    db.clear_history(update.effective_chat.id)
    await update.message.reply_text("تم مسح سجل المحادثة ✅")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أي رسالة نصية عادية من المستخدم"""
    chat_id = update.effective_chat.id
    user_text = update.message.text

    db.add_message(chat_id, "user", user_text)
    history = db.get_history(chat_id, limit=MAX_HISTORY_MESSAGES)

    # إظهار "يكتب..." أثناء المعالجة
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        reply_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
    except Exception as e:
        logger.error(f"خطأ أثناء استدعاء Claude: {e}")
        reply_text = "عذراً، صار خطأ أثناء معالجة طلبك. حاول مرة ثانية."

    db.add_message(chat_id, "assistant", reply_text)
    await update.message.reply_text(reply_text)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """استقبال ملف PDF أو Word أو PowerPoint وتحديد نوع التحويل المطلوب"""
    document = update.message.document
    file_name = document.file_name or ""
    ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""

    if ext == "pdf":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "تحويل إلى Word", callback_data=f"pdf2docx|{document.file_id}"
                    ),
                    InlineKeyboardButton(
                        "تحويل إلى PowerPoint",
                        callback_data=f"pdf2pptx|{document.file_id}",
                    ),
                ]
            ]
        )
        await update.message.reply_text("اختر نوع التحويل:", reply_markup=keyboard)
    elif ext in ("docx", "doc"):
        await convert_and_send(update, context, document.file_id, file_name, "docx2pdf")
    elif ext in ("pptx", "ppt"):
        await convert_and_send(update, context, document.file_id, file_name, "pptx2pdf")
    else:
        await update.message.reply_text(
            "أدعم حالياً ملفات PDF وWord (.docx) وPowerPoint (.pptx) فقط."
        )


async def handle_conversion_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """معالجة اختيار المستخدم من أزرار التحويل"""
    query = update.callback_query
    await query.answer()
    conversion_type, file_id = query.data.split("|", 1)
    await convert_and_send(
        update, context, file_id, "file", conversion_type, from_callback=True
    )


async def convert_and_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    file_name: str,
    conversion_type: str,
    from_callback: bool = False,
) -> None:
    """تنزيل الملف، تحويله، وإرساله للمستخدم"""
    chat_id = update.effective_chat.id
    message = update.callback_query.message if from_callback else update.message

    conversions = {
        "pdf2docx": (".pdf", ".docx", converters.pdf_to_docx),
        "pdf2pptx": (".pdf", ".pptx", converters.pdf_to_pptx),
        "docx2pdf": (".docx", ".pdf", converters.docx_to_pdf),
        "pptx2pdf": (".pptx", ".pdf", converters.pptx_to_pdf),
    }
    src_ext, dst_ext, convert_func = conversions[conversion_type]

    await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
    if from_callback:
        await message.reply_text("جاري التحويل... ⏳")
    else:
        await message.reply_text("جاري التحويل... ⏳")

    src_path = os.path.join(TEMP_DIR, f"{chat_id}_{file_id}{src_ext}")
    dst_path = os.path.join(TEMP_DIR, f"{chat_id}_{file_id}{dst_ext}")

    try:
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(src_path)

        convert_func(src_path, dst_path)

        await context.bot.send_document(chat_id=chat_id, document=open(dst_path, "rb"))
    except Exception as e:
        logger.error(f"خطأ أثناء التحويل: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="عذراً، صار خطأ أثناء التحويل. تأكد إن الملف سليم."
        )
    finally:
        for path in (src_path, dst_path):
            if os.path.exists(path):
                os.remove(path)


def main() -> None:
    if (
        not TELEGRAM_TOKEN
        or not ANTHROPIC_API_KEY
        or TELEGRAM_TOKEN == "ضع_توكن_البوت_هنا"
        or ANTHROPIC_API_KEY == "ضع_مفتاح_Anthropic_هنا"
    ):
        raise RuntimeError(
            "لازم تحط التوكن الحقيقي ومفتاح Anthropic في أعلى ملف bot.py "
            "(أو في ملف .env)"
        )

    db.init_db()
    keep_alive()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_conversion_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("البوت شغال...")
    app.run_polling()


if __name__ == "__main__":
    main()
