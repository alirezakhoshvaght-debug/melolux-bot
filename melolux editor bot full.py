"""
بات ادیت موزیک ملولوکس - نسخه‌ی کامل
======================================
شبیه‌سازی شده بر اساس منوی بات‌های معروف ادیت موزیک تلگرام.

قابلیت‌ها:
- ✏️ ادیت تگ‌ها: عنوان، خواننده، آلبوم، سال، ژانر، شماره ترک، کاور، کامنت، آلبوم آرتیست، آهنگساز، ناشر
- ✂️ برش (Cut): جدا کردن بخشی از آهنگ با زمان شروع/پایان
- 🎚 تنظیم بیت‌ریت (Set Bitrate)
- 🔊 تنظیم ولوم (Volume)
- 🎧 افکت 8D (پنینگ چرخشی)
- 🎤 تبدیل به ویس (Convert to Voice)
- ✍️ تغییر کپشن
- 📌 اعمال تنظیمات پیش‌فرض ذخیره‌شده (اسم/کاور چنل) با یک دکمه

نیازمندی‌ها:
    pip install python-telegram-bot --upgrade
    pip install mutagen
    # ffmpeg باید نصب باشد:
    #   Ubuntu/Debian: sudo apt install ffmpeg
    #   Mac: brew install ffmpeg
    #   Windows: از سایت ffmpeg.org دانلود و به PATH اضافه کن

⚠️ محدودیت تلگرام (نه این کد): بات‌های معمولی حداکثر ۲۰ مگابایت دانلود
و ۵۰ مگابایت آپلود می‌توانند انجام دهند. برای رفع این محدودیت باید یک
Local Bot API Server راه‌اندازی شود (مرحله‌ی جداگانه).
"""

import json
import logging
import subprocess
from pathlib import Path

from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, APIC, COMM, TPE2, TCOM, TPUB, ID3NoHeaderError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== تنظیمات =====
BOT_TOKEN = "8971547320:AAHnV4V0sqRFqmzk0VHJJCt05TCE8Ey4-VY"
# ====================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

TAG_FIELDS = {
    "title": ("🎵 عنوان", TIT2),
    "artist": ("👤 خواننده", TPE1),
    "album": ("📁 آلبوم", TALB),
    "year": ("📅 سال", TDRC),
    "genre": ("🎙 ژانر", TCON),
    "track": ("💿 شماره ترک", TRCK),
    "comment": ("📝 کامنت", None),   # جدا هندل می‌شود
    "album_artist": ("👥 آلبوم آرتیست", TPE2),
    "composer": ("🧑‍💻 آهنگساز", TCOM),
    "publisher": ("👤 ناشر", TPUB),
}


# ---------- ذخیره‌سازی تنظیمات کاربر ----------

def user_settings_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


def load_user_settings(user_id: int) -> dict:
    path = user_settings_path(user_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"artist": None, "cover_path": None}


def save_user_settings(user_id: int, settings: dict):
    user_settings_path(user_id).write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- دستورات پایه ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "سلام! 🎵 بات ادیت موزیک ملولوکس در خدمتته.\n\n"
        "اول تنظیمات پیش‌فرضت رو ذخیره کن:\n"
        "• /setartist <اسم> — اسم پیش‌فرض چنل/خواننده\n"
        "• عکس بفرست و ریپلای کن با /setcover — کاور پیش‌فرض\n"
        "• /myinfo — دیدن تنظیمات فعلی\n\n"
        "بعدش یه فایل MP3 بفرست تا منوی ادیت باز شه 🎛"
    )
    await update.message.reply_text(text)


async def set_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("مثال:\n/setartist Melolux")
        return
    settings = load_user_settings(update.effective_user.id)
    settings["artist"] = " ".join(context.args)
    save_user_settings(update.effective_user.id, settings)
    await update.message.reply_text(f"✅ ذخیره شد: {settings['artist']}")


async def set_cover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    photo = message.photo[-1] if message.photo else (
        message.reply_to_message.photo[-1] if message.reply_to_message and message.reply_to_message.photo else None
    )
    if not photo:
        await update.message.reply_text("یه عکس بفرست یا روی عکس ریپلای کن و دوباره /setcover بزن.")
        return
    user_id = update.effective_user.id
    file = await context.bot.get_file(photo.file_id)
    cover_path = TEMP_DIR / f"cover_{user_id}.jpg"
    await file.download_to_drive(custom_path=str(cover_path))
    settings = load_user_settings(user_id)
    settings["cover_path"] = str(cover_path)
    save_user_settings(user_id, settings)
    await update.message.reply_text("✅ کاور پیش‌فرض ذخیره شد.")


async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = load_user_settings(update.effective_user.id)
    artist = settings.get("artist") or "— ثبت نشده —"
    cover = "دارد ✅" if settings.get("cover_path") and Path(settings["cover_path"]).exists() else "ندارد ❌"
    await update.message.reply_text(f"📋 اسم پیش‌فرض: {artist}\nکاور پیش‌فرض: {cover}")


# ---------- منوی اصلی ادیت ----------

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ ادیت تگ‌ها", callback_data="menu_tags")],
        [InlineKeyboardButton("✂️ برش (Cut)", callback_data="action_cut")],
        [InlineKeyboardButton("🎚 تنظیم بیت‌ریت", callback_data="menu_bitrate")],
        [InlineKeyboardButton("🔊 ولوم", callback_data="menu_volume")],
        [InlineKeyboardButton("🎧 افکت 8D", callback_data="action_8d")],
        [InlineKeyboardButton("🎤 تبدیل به ویس", callback_data="action_voice")],
        [InlineKeyboardButton("📌 اعمال تنظیمات پیش‌فرض", callback_data="action_apply_default")],
        [InlineKeyboardButton("🎬 دموی ۴۵ ثانیه‌ای", callback_data="action_demo")],
        [InlineKeyboardButton("✅ ارسال فایل نهایی", callback_data="action_finish")],
    ])


def tags_menu_keyboard():
    rows, row = [], []
    for key, (label, _) in TAG_FIELDS.items():
        row.append(InlineKeyboardButton(label, callback_data=f"tag_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🖼 کاور", callback_data="tag_picture")])
    rows.append([InlineKeyboardButton("🗑 پاک کردن همه‌ی تگ‌ها", callback_data="tag_remove_all")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def bitrate_keyboard():
    presets = [128, 192, 256, 320]
    row = [InlineKeyboardButton(f"{b} kbps", callback_data=f"bitrate_{b}") for b in presets]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]])


def volume_keyboard():
    presets = [50, 75, 100, 125, 150, 200]
    rows = [[InlineKeyboardButton(f"{v}%", callback_data=f"volume_{v}") for v in presets[i:i+3]]
            for i in range(0, len(presets), 3)]
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ---------- دریافت فایل صوتی ----------

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    audio = message.audio or message.document
    if audio is None:
        return

    user_id = update.effective_user.id
    file = await context.bot.get_file(audio.file_id)
    raw_path = TEMP_DIR / f"raw_{user_id}.mp3"
    await file.download_to_drive(custom_path=str(raw_path))

    # تبدیل خودکار به کیفیت ۳۲۰kbps به‌عنوان پیش‌فرض خروجی
    work_path = TEMP_DIR / f"work_{user_id}.mp3"
    await message.reply_text("⏳ در حال آماده‌سازی با کیفیت ۳۲۰kbps...")
    _run(["ffmpeg", "-y", "-i", str(raw_path), "-b:a", "320k", str(work_path)])
    raw_path.unlink(missing_ok=True)

    context.user_data["work_path"] = str(work_path)
    context.user_data["caption"] = ""
    context.user_data["awaiting"] = None

    await message.reply_text(
        "🎧 فایل با کیفیت ۳۲۰kbps آماده شد! از منوی زیر انتخاب کن:",
        reply_markup=main_menu_keyboard(),
    )


# ---------- روتر دکمه‌ها ----------

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if "work_path" not in context.user_data and data not in ("back_main",):
        await query.edit_message_text("اول یه فایل MP3 بفرست.")
        return

    if data == "back_main":
        await query.edit_message_text("منوی ادیت:", reply_markup=main_menu_keyboard())

    elif data == "menu_tags":
        await query.edit_message_text("کدوم تگ رو می‌خوای ادیت کنی؟", reply_markup=tags_menu_keyboard())

    elif data.startswith("tag_"):
        field = data.replace("tag_", "")
        if field == "remove_all":
            await remove_all_tags(context)
            await query.edit_message_text("✅ همه‌ی تگ‌ها پاک شد.", reply_markup=main_menu_keyboard())
        elif field == "picture":
            context.user_data["awaiting"] = "tag_picture"
            await query.edit_message_text("عکس کاور جدید رو بفرست:")
        else:
            context.user_data["awaiting"] = f"tag_{field}"
            label = TAG_FIELDS[field][0]
            await query.edit_message_text(f"{label} جدید رو بفرست:")

    elif data == "menu_bitrate":
        await query.edit_message_text("بیت‌ریت مورد نظر رو انتخاب کن:", reply_markup=bitrate_keyboard())

    elif data.startswith("bitrate_"):
        bitrate = data.replace("bitrate_", "")
        await query.edit_message_text("⏳ در حال اعمال بیت‌ریت...")
        await run_ffmpeg_bitrate(context, bitrate)
        await query.edit_message_text(f"✅ بیت‌ریت روی {bitrate}kbps تنظیم شد.", reply_markup=main_menu_keyboard())

    elif data == "menu_volume":
        await query.edit_message_text("ولوم مورد نظر رو انتخاب کن:", reply_markup=volume_keyboard())

    elif data.startswith("volume_"):
        percent = int(data.replace("volume_", ""))
        await query.edit_message_text("⏳ در حال تنظیم ولوم...")
        await run_ffmpeg_volume(context, percent)
        await query.edit_message_text(f"✅ ولوم روی {percent}% تنظیم شد.", reply_markup=main_menu_keyboard())

    elif data == "action_cut":
        context.user_data["awaiting"] = "cut"
        await query.edit_message_text(
            "زمان شروع و پایان رو به ثانیه بفرست، مثال:\n30-90\n(یعنی از ثانیه‌ی ۳۰ تا ۹۰)"
        )

    elif data == "action_8d":
        await query.edit_message_text("⏳ در حال ساخت افکت 8D...")
        await run_ffmpeg_8d(context)
        await query.edit_message_text("✅ افکت 8D اعمال شد.", reply_markup=main_menu_keyboard())

    elif data == "action_voice":
        await query.edit_message_text("⏳ در حال تبدیل به ویس...")
        ogg_path = await run_ffmpeg_to_voice(context)
        await context.bot.send_voice(chat_id=update.effective_chat.id, voice=open(ogg_path, "rb"))
        await query.edit_message_text("✅ فایل ویس ارسال شد.", reply_markup=main_menu_keyboard())

    elif data == "action_apply_default":
        settings = load_user_settings(user_id)
        await apply_default_tags(context, settings)
        await query.edit_message_text("✅ اسم و کاور پیش‌فرض اعمال شد.", reply_markup=main_menu_keyboard())

    elif data == "action_demo":
        await query.edit_message_text("⏳ در حال ساخت دموی ۴۵ ثانیه‌ای...")
        demo_path = await make_demo(context)
        await context.bot.send_audio(chat_id=update.effective_chat.id, audio=open(demo_path, "rb"),
                                      caption="🎬 دموی ۴۵ ثانیه‌ای")
        await query.edit_message_text("منوی ادیت:", reply_markup=main_menu_keyboard())

    elif data == "action_finish":
        work_path = Path(context.user_data["work_path"])
        caption = context.user_data.get("caption") or "✅ فایل نهایی"
        await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=open(work_path, "rb"),
            caption=caption,
        )
        await query.edit_message_text("فایل نهایی ارسال شد 🎉 برای فایل بعدی، یه MP3 دیگه بفرست.")


# ---------- دریافت متن (برای مقادیر تگ / برش / کپشن) ----------

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        return

    text = update.message.text.strip()

    if awaiting == "cut":
        try:
            start_s, end_s = map(int, text.replace(" ", "").split("-"))
        except Exception:
            await update.message.reply_text("فرمت اشتباهه. مثال درست: 30-90")
            return
        await update.message.reply_text("⏳ در حال برش...")
        await run_ffmpeg_cut(context, start_s, end_s)
        context.user_data["awaiting"] = None
        await update.message.reply_text("✅ برش انجام شد.", reply_markup=main_menu_keyboard())
        return

    if awaiting.startswith("tag_"):
        field = awaiting.replace("tag_", "")
        set_single_tag(context, field, text)
        context.user_data["awaiting"] = None
        await update.message.reply_text(f"✅ ذخیره شد.", reply_markup=main_menu_keyboard())
        return

    if awaiting == "caption":
        context.user_data["caption"] = text
        context.user_data["awaiting"] = None
        await update.message.reply_text("✅ کپشن ذخیره شد.", reply_markup=main_menu_keyboard())
        return


async def handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting") != "tag_picture":
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    user_id = update.effective_user.id
    img_path = TEMP_DIR / f"newcover_{user_id}.jpg"
    await file.download_to_drive(custom_path=str(img_path))
    set_cover_tag(context, img_path)
    context.user_data["awaiting"] = None
    await update.message.reply_text("✅ کاور جدید اعمال شد.", reply_markup=main_menu_keyboard())


# ---------- توابع تگ‌گذاری (mutagen) ----------

def _load_tags(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def set_single_tag(context, field: str, value: str):
    path = Path(context.user_data["work_path"])
    tags = _load_tags(path)
    if field == "comment":
        tags["COMM"] = COMM(encoding=3, lang="eng", desc="", text=value)
    else:
        _, frame_cls = TAG_FIELDS[field]
        frame_id = frame_cls.__name__
        tags[frame_id] = frame_cls(encoding=3, text=value)
    tags.save(path)


def set_cover_tag(context, img_path: Path):
    path = Path(context.user_data["work_path"])
    tags = _load_tags(path)
    with open(img_path, "rb") as img:
        tags["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img.read())
    tags.save(path)


async def remove_all_tags(context):
    path = Path(context.user_data["work_path"])
    tags = _load_tags(path)
    tags.delete(path)


async def apply_default_tags(context, settings: dict):
    path = Path(context.user_data["work_path"])
    tags = _load_tags(path)
    if settings.get("artist"):
        tags["TPE1"] = TPE1(encoding=3, text=settings["artist"])
    if settings.get("cover_path") and Path(settings["cover_path"]).exists():
        with open(settings["cover_path"], "rb") as img:
            tags["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img.read())
    tags.save(path)


# ---------- توابع پردازش صوت (ffmpeg) ----------

def _run(cmd: list):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def run_ffmpeg_cut(context, start_s: int, end_s: int):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"cut_{path.name}"
    _run(["ffmpeg", "-y", "-i", str(path), "-ss", str(start_s), "-to", str(end_s), "-c", "copy", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_bitrate(context, bitrate: str):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"br_{path.name}"
    _run(["ffmpeg", "-y", "-i", str(path), "-b:a", f"{bitrate}k", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_volume(context, percent: int):
    path = Path(context.user_data["work_path"])
    factor = percent / 100
    out_path = TEMP_DIR / f"vol_{path.name}"
    _run(["ffmpeg", "-y", "-i", str(path), "-filter:a", f"volume={factor}", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_8d(context):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"8d_{path.name}"
    # افکت پنینگ چرخشی (شبیه‌سازی 8D)
    _run(["ffmpeg", "-y", "-i", str(path), "-af", "apulsator=hz=0.09", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_to_voice(context) -> Path:
    path = Path(context.user_data["work_path"])
    ogg_path = TEMP_DIR / f"voice_{path.stem}.ogg"
    _run(["ffmpeg", "-y", "-i", str(path), "-c:a", "libopus", "-b:a", "64k", str(ogg_path)])
    return ogg_path


async def make_demo(context) -> Path:
    path = Path(context.user_data["work_path"])
    # طول کل فایل رو با ffprobe می‌گیریم
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())
    demo_len = 45
    start = max(0, (duration - demo_len) / 2)
    demo_path = TEMP_DIR / f"demo_{path.name}"
    _run(["ffmpeg", "-y", "-i", str(path), "-ss", str(start), "-t", str(demo_len), "-c", "copy", str(demo_path)])
    return demo_path


# ---------- اجرای بات ----------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setartist", set_artist))
    app.add_handler(CommandHandler("setcover", set_cover))
    app.add_handler(CommandHandler("myinfo", my_info))

    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_input))

    logger.info("بات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
