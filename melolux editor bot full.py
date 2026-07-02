"""
Melolux Music Editor Bot - Bilingual (Persian/English) Full Version
بات ادیت موزیک ملولوکس - نسخه‌ی کامل دوزبانه (فارسی/انگلیسی)
======================================================================
Requirements / نیازمندی‌ها:
    pip install python-telegram-bot --upgrade
    pip install mutagen
    ffmpeg must be installed (ffmpeg باید نصب باشد):
      Ubuntu/Debian: sudo apt install ffmpeg
      Mac: brew install ffmpeg
      Windows: from ffmpeg.org and add to PATH

⚠️ Telegram limit (not this code): normal bots can download up to 20MB
and upload up to 50MB. To remove this, a Local Bot API Server is needed.
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, APIC, COMM, TPE2, TCOM, TPUB, ID3NoHeaderError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== SETTINGS / تنظیمات =====
def _clean_token(raw: str) -> str:
    """پاک کردن فاصله، خط جدید و کاراکترهای نامرئی از توکن."""
    if not raw:
        return raw
    # حذف کاراکترهای کنترلی/نامرئی یونیکد (bidi marks و مشابه)
    cleaned = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\s]', '', raw)
    return cleaned


BOT_TOKEN = _clean_token(
    os.environ.get("BOT_TOKEN") or "8971547320:AAFNTC0ySSgdQpgUJ2eGw4hlRY-L74wts88"
)
DEFAULT_LANG = "fa"  # زبان پیش‌فرض برای کاربران جدید
REQUIRED_CHANNEL = "@melolux"  # کانالی که کاربر باید عضوش باشه
# ================================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# ---------- تگ‌ها به هر دو زبان ----------
TAG_FIELDS = {
    "title":         {"fa": "🎵 عنوان",        "en": "🎵 Title",        "frame": TIT2},
    "artist":        {"fa": "👤 خواننده",      "en": "👤 Artist",       "frame": TPE1},
    "album":         {"fa": "📁 آلبوم",        "en": "📁 Album",        "frame": TALB},
    "year":          {"fa": "📅 سال",          "en": "📅 Year",         "frame": TDRC},
    "genre":         {"fa": "🎙 ژانر",         "en": "🎙 Genre",        "frame": TCON},
    "track":         {"fa": "💿 شماره ترک",    "en": "💿 Track No.",    "frame": TRCK},
    "comment":       {"fa": "📝 کامنت",        "en": "📝 Comment",      "frame": None},
    "album_artist":  {"fa": "👥 آلبوم آرتیست", "en": "👥 Album Artist", "frame": TPE2},
    "composer":      {"fa": "🧑‍💻 آهنگساز",     "en": "🧑‍💻 Composer",    "frame": TCOM},
    "publisher":     {"fa": "👤 ناشر",         "en": "👤 Publisher",    "frame": TPUB},
}

# ---------- سبک‌های موزیک برای قالب کپشن (هشتگ‌ها) ----------
GENRE_LIST = {
    "blues":        {"emoji": "🎷", "fa": "بلوز",     "en": "Blues",
                      "tag_fa": "حس کلاسیک، طعم ابدی.", "tag_en": "Classic vibes, timeless taste."},
    "pop":          {"emoji": "🎤", "fa": "پاپ",       "en": "Pop",
                      "tag_fa": "صدای امروز، حس همیشگی.", "tag_en": "Today's sound, timeless feeling."},
    "rap":          {"emoji": "🎧", "fa": "رپ",        "en": "Rap",
                      "tag_fa": "ریتم خیابون، کلام خالص.", "tag_en": "Street rhythm, raw words."},
    "rock":         {"emoji": "🎸", "fa": "راک",       "en": "Rock",
                      "tag_fa": "صدای بلند، احساس واقعی.", "tag_en": "Loud sound, real feeling."},
    "electronic":   {"emoji": "🎹", "fa": "الکترونیک", "en": "Electronic",
                      "tag_fa": "موج دیجیتال، انرژی بی‌پایان.", "tag_en": "Digital wave, endless energy."},
    "sad":          {"emoji": "💔", "fa": "غمگین",     "en": "Sad",
                      "tag_fa": "حس غمگین، لحظه‌ی سکوت.", "tag_en": "Sad feeling, a moment of silence."},
    "happy":        {"emoji": "✨", "fa": "شاد",       "en": "Happy",
                      "tag_fa": "انرژی مثبت، لحظه‌ی شادی.", "tag_en": "Positive energy, a joyful moment."},
    "chill":        {"emoji": "🌙", "fa": "چیل",       "en": "Chill",
                      "tag_fa": "آرامش خالص، لحظه‌ی ریلکس.", "tag_en": "Pure calm, a relaxing moment."},
    "instrumental": {"emoji": "🎼", "fa": "بی‌کلام",   "en": "Instrumental",
                      "tag_fa": "فقط ملودی، بدون کلام.", "tag_en": "Just melody, no words."},
    "persian":      {"emoji": "🪕", "fa": "ایرانی",    "en": "Persian",
                      "tag_fa": "رنگ ایرانی، حس آشنا.", "tag_en": "Persian color, familiar feeling."},
    "trap":         {"emoji": "🔥", "fa": "ترپ",       "en": "Trap",
                      "tag_fa": "بیت سنگین، انرژی خام.", "tag_en": "Heavy beat, raw energy."},
    "rnb":          {"emoji": "💫", "fa": "آر اند بی", "en": "R&B",
                      "tag_fa": "صدای نرم، احساس عمیق.", "tag_en": "Smooth sound, deep feeling."},
}


# ---------- چند شعار کوتاه برای هر سبک (قابل انتخاب) ----------
SLOGANS = {
    "blues":        [{"fa": "حس کلاسیک، طعم ابدی.", "en": "Classic vibes, timeless taste."},
                      {"fa": "بلوز خالص، احساس عمیق.", "en": "Pure blues, deep feeling."},
                      {"fa": "صدای قدیم، حس همیشگی.", "en": "Old sound, timeless soul."}],
    "pop":          [{"fa": "صدای امروز، حس همیشگی.", "en": "Today's sound, timeless feeling."},
                      {"fa": "ریتم تازه، انرژی ناب.", "en": "Fresh rhythm, pure energy."},
                      {"fa": "ملودی روز، حس خاص.", "en": "Sound of the day, special vibe."}],
    "rap":          [{"fa": "ریتم خیابون، کلام خالص.", "en": "Street rhythm, raw words."},
                      {"fa": "بار سنگین، پیام واقعی.", "en": "Heavy bars, real message."},
                      {"fa": "فلوی خاص، حس اورجینال.", "en": "Unique flow, original feel."}],
    "rock":         [{"fa": "صدای بلند، احساس واقعی.", "en": "Loud sound, real feeling."},
                      {"fa": "انرژی خام، ریتم آتیشی.", "en": "Raw energy, fiery rhythm."},
                      {"fa": "گیتار بلند، حس آزاد.", "en": "Loud guitar, free spirit."}],
    "electronic":   [{"fa": "موج دیجیتال، انرژی بی‌پایان.", "en": "Digital wave, endless energy."},
                      {"fa": "بیت الکترونیک، حس آینده.", "en": "Electronic beat, future feel."},
                      {"fa": "ریتم مصنوعی، احساس واقعی.", "en": "Synthetic rhythm, real feeling."}],
    "sad":          [{"fa": "حس غمگین، لحظه‌ی سکوت.", "en": "Sad feeling, a moment of silence."},
                      {"fa": "دل‌تنگی آروم، شب‌های تنها.", "en": "Quiet longing, lonely nights."},
                      {"fa": "بغض ساکت، حس عمیق.", "en": "Silent ache, deep emotion."}],
    "happy":        [{"fa": "انرژی مثبت، لحظه‌ی شادی.", "en": "Positive energy, a joyful moment."},
                      {"fa": "حس خوب، ریتم شاد.", "en": "Good vibes, happy rhythm."},
                      {"fa": "لبخند صدادار، انرژی تازه.", "en": "Sound of a smile, fresh energy."}],
    "chill":        [{"fa": "آرامش خالص، لحظه‌ی ریلکس.", "en": "Pure calm, a relaxing moment."},
                      {"fa": "ریتم آروم، حس سبک.", "en": "Slow rhythm, light feeling."},
                      {"fa": "سکوت شیرین، صدای آروم.", "en": "Sweet silence, gentle sound."}],
    "instrumental": [{"fa": "فقط ملودی، بدون کلام.", "en": "Just melody, no words."},
                      {"fa": "صدای ساز، حس خالص.", "en": "Sound of the instrument, pure feel."},
                      {"fa": "ملودی ناب، بدون کلمه.", "en": "Pure melody, wordless."}],
    "persian":      [{"fa": "رنگ ایرانی، حس آشنا.", "en": "Persian color, familiar feeling."},
                      {"fa": "صدای وطن، حس نوستالژی.", "en": "Sound of home, nostalgic feel."},
                      {"fa": "ملودی ایرانی، حس ناب.", "en": "Persian melody, pure feeling."}],
    "trap":         [{"fa": "بیت سنگین، انرژی خام.", "en": "Heavy beat, raw energy."},
                      {"fa": "بیس سنگین، حس خیابون.", "en": "Heavy bass, street feel."},
                      {"fa": "ریتم تاریک، انرژی بالا.", "en": "Dark rhythm, high energy."}],
    "rnb":          [{"fa": "صدای نرم، احساس عمیق.", "en": "Smooth sound, deep feeling."},
                      {"fa": "ملودی نرم، حس گرم.", "en": "Smooth melody, warm feel."},
                      {"fa": "ریتم آروم، احساس ناب.", "en": "Gentle rhythm, pure emotion."}],
}


# ---------- دیکشنری کامل متن‌ها ----------
T = {
    "choose_lang": {
        "fa": "🌐 لطفاً زبان مورد نظرت رو انتخاب کن:",
        "en": "🌐 Please choose your language:",
    },
    "lang_set": {
        "fa": "✅ زبان روی فارسی تنظیم شد.",
        "en": "✅ Language set to English.",
    },
    "start": {
        "fa": (
            "سلام! 🎵 بات ادیت موزیک ملولوکس در خدمتته.\n\n"
            "اول تنظیمات پیش‌فرضت رو ذخیره کن:\n"
            "• /setartist <اسم> — اسم پیش‌فرض چنل/خواننده\n"
            "• عکس بفرست و ریپلای کن با /setcover — کاور پیش‌فرض\n"
            "• /myinfo — دیدن تنظیمات فعلی\n"
            "• /language — تغییر زبان بات\n\n"
            "بعدش یه فایل MP3 بفرست تا منوی ادیت باز شه 🎛"
        ),
        "en": (
            "Hello! 🎵 Welcome to the Melolux Music Editor Bot.\n\n"
            "First, save your default settings:\n"
            "• /setartist <name> — default channel/artist name\n"
            "• Send a photo and reply to it with /setcover — default cover\n"
            "• /myinfo — view current settings\n"
            "• /language — change bot language\n\n"
            "Then send an MP3 file to open the edit menu 🎛"
        ),
    },
    "setartist_usage": {
        "fa": "مثال:\n/setartist Melolux",
        "en": "Example:\n/setartist Melolux",
    },
    "artist_saved": {
        "fa": "✅ ذخیره شد: {value}",
        "en": "✅ Saved: {value}",
    },
    "setcover_prompt": {
        "fa": "یه عکس بفرست یا روی عکس ریپلای کن و دوباره /setcover بزن.",
        "en": "Send a photo, or reply to one and run /setcover again.",
    },
    "cover_saved": {
        "fa": "✅ کاور پیش‌فرض ذخیره شد.",
        "en": "✅ Default cover saved.",
    },
    "myinfo": {
        "fa": "📋 اسم پیش‌فرض: {artist}\nکاور پیش‌فرض: {cover}",
        "en": "📋 Default name: {artist}\nDefault cover: {cover}",
    },
    "not_set": {"fa": "— ثبت نشده —", "en": "— not set —"},
    "has_it": {"fa": "دارد ✅", "en": "Yes ✅"},
    "no_it": {"fa": "ندارد ❌", "en": "No ❌"},

    "menu_tags": {"fa": "✏️ ادیت تگ‌ها", "en": "✏️ Edit Tags"},
    "menu_cut": {"fa": "✂️ برش (Cut)", "en": "✂️ Cut"},
    "menu_bitrate": {"fa": "🎚 تنظیم بیت‌ریت", "en": "🎚 Set Bitrate"},
    "menu_volume": {"fa": "🔊 ولوم", "en": "🔊 Volume"},
    "menu_8d": {"fa": "🎧 افکت 8D", "en": "🎧 8D Effect"},
    "menu_voice": {"fa": "🎤 تبدیل به ویس", "en": "🎤 Convert to Voice"},
    "menu_default": {"fa": "📌 اعمال تنظیمات پیش‌فرض", "en": "📌 Apply Default Settings"},
    "menu_demo": {"fa": "🎬 دموی ۴۵ ثانیه‌ای", "en": "🎬 45s Demo"},
    "menu_finish": {"fa": "✅ ارسال فایل نهایی", "en": "✅ Send Final File"},
    "menu_picture": {"fa": "🖼 کاور", "en": "🖼 Picture"},
    "menu_remove_all": {"fa": "🗑 پاک کردن همه‌ی تگ‌ها", "en": "🗑 Remove All Tags"},
    "menu_back": {"fa": "🔙 بازگشت", "en": "🔙 Back"},

    "need_file": {"fa": "اول یه فایل MP3 بفرست.", "en": "Send an MP3 file first."},
    "main_menu_title": {"fa": "منوی ادیت:", "en": "Edit menu:"},
    "which_tag": {"fa": "کدوم تگ رو می‌خوای ادیت کنی؟", "en": "Which tag do you want to edit?"},
    "all_tags_removed": {"fa": "✅ همه‌ی تگ‌ها پاک شد.", "en": "✅ All tags removed."},
    "send_new_cover": {"fa": "عکس کاور جدید رو بفرست:", "en": "Send the new cover photo:"},
    "send_new_value": {"fa": "{label} جدید رو بفرست:", "en": "Send the new {label}:"},
    "choose_bitrate": {"fa": "بیت‌ریت مورد نظر رو انتخاب کن:", "en": "Choose the desired bitrate:"},
    "applying_bitrate": {"fa": "⏳ در حال اعمال بیت‌ریت...", "en": "⏳ Applying bitrate..."},
    "bitrate_done": {"fa": "✅ بیت‌ریت روی {bitrate}kbps تنظیم شد.", "en": "✅ Bitrate set to {bitrate}kbps."},
    "choose_volume": {"fa": "ولوم مورد نظر رو انتخاب کن:", "en": "Choose the desired volume:"},
    "applying_volume": {"fa": "⏳ در حال تنظیم ولوم...", "en": "⏳ Adjusting volume..."},
    "volume_done": {"fa": "✅ ولوم روی {percent}% تنظیم شد.", "en": "✅ Volume set to {percent}%."},
    "cut_prompt": {
        "fa": "زمان شروع و پایان رو به ثانیه بفرست، مثال:\n30-90\n(یعنی از ثانیه‌ی ۳۰ تا ۹۰)",
        "en": "Send start and end time in seconds, example:\n30-90\n(meaning from second 30 to 90)",
    },
    "cut_bad_format": {"fa": "فرمت اشتباهه. مثال درست: 30-90", "en": "Wrong format. Correct example: 30-90"},
    "cutting": {"fa": "⏳ در حال برش...", "en": "⏳ Cutting..."},
    "cut_done": {"fa": "✅ برش انجام شد.", "en": "✅ Cut completed."},
    "applying_8d": {"fa": "⏳ در حال ساخت افکت 8D...", "en": "⏳ Applying 8D effect..."},
    "done_8d": {"fa": "✅ افکت 8D اعمال شد.", "en": "✅ 8D effect applied."},
    "converting_voice": {"fa": "⏳ در حال تبدیل به ویس...", "en": "⏳ Converting to voice..."},
    "voice_sent": {"fa": "✅ فایل ویس ارسال شد.", "en": "✅ Voice file sent."},
    "default_applied": {"fa": "✅ اسم و کاور پیش‌فرض اعمال شد.", "en": "✅ Default name and cover applied."},
    "making_demo": {"fa": "⏳ در حال ساخت دموی ۴۵ ثانیه‌ای...", "en": "⏳ Creating 45s demo..."},
    "demo_caption": {"fa": "🎬 دموی ۴۵ ثانیه‌ای", "en": "🎬 45-second demo"},
    "final_sent": {
        "fa": "فایل نهایی ارسال شد 🎉 برای فایل بعدی، یه MP3 دیگه بفرست.",
        "en": "Final file sent 🎉 Send another MP3 for the next one.",
    },
    "final_caption_default": {"fa": "✅ فایل نهایی", "en": "✅ Final file"},
    "value_saved": {"fa": "✅ ذخیره شد.", "en": "✅ Saved."},
    "caption_saved": {"fa": "✅ کپشن ذخیره شد.", "en": "✅ Caption saved."},
    "new_cover_applied": {"fa": "✅ کاور جدید اعمال شد.", "en": "✅ New cover applied."},
    "receiving_file": {
        "fa": "⏳ در حال آماده‌سازی با کیفیت ۳۲۰kbps...",
        "en": "⏳ Preparing at 320kbps quality...",
    },
    "file_ready": {
        "fa": "🎧 فایل با کیفیت ۳۲۰kbps آماده شد! از منوی زیر انتخاب کن:",
        "en": "🎧 File ready at 320kbps! Choose from the menu below:",
    },
    "menu_caption_template": {"fa": "🏷 قالب کپشن + هشتگ", "en": "🏷 Caption Template + Hashtags"},
    "choose_genres": {
        "fa": "سبک‌(های) موزیک رو انتخاب کن (می‌تونی چندتا بزنی)، بعد «✅ تایید» رو بزن:",
        "en": "Choose the music genre(s) (you can pick multiple), then tap \"✅ Done\":",
    },
    "genre_done_btn": {"fa": "✅ تایید", "en": "✅ Done"},
    "no_genre_selected": {
        "fa": "⚠️ حداقل یه سبک انتخاب کن.",
        "en": "⚠️ Please select at least one genre.",
    },
    "choose_slogan": {
        "fa": "یکی از این شعارهای کوتاه رو انتخاب کن:",
        "en": "Choose one of these short slogans:",
    },
    "ask_year": {
        "fa": "سال تولید رو بفرست (یا برای سال {current_year} همین دکمه رو بزن):",
        "en": "Send the production year (or tap this button for {current_year}):",
    },
    "use_current_year": {"fa": "📅 همین سال ({current_year})", "en": "📅 This year ({current_year})"},
    "caption_template_ready": {
        "fa": "✅ کپشن آماده شد و ذخیره شد. موقع ارسال فایل نهایی همراهش می‌ره.",
        "en": "✅ Caption template ready and saved. It will be sent with the final file.",
    },
    "join_required": {
        "fa": "🔒 برای استفاده از بات، اول باید عضو کانال ما بشی:",
        "en": "🔒 To use this bot, please join our channel first:",
    },
    "join_button": {"fa": "📢 عضویت در کانال", "en": "📢 Join Channel"},
    "check_join_button": {"fa": "✅ عضو شدم، بررسی کن", "en": "✅ I've joined, check"},
    "still_not_joined": {
        "fa": "❌ هنوز عضو کانال نیستی. اول عضو شو، بعد دوباره بررسی کن.",
        "en": "❌ You haven't joined yet. Please join first, then check again.",
    },
    "join_confirmed": {
        "fa": "✅ عضویت تایید شد! حالا می‌تونی از بات استفاده کنی.",
        "en": "✅ Membership confirmed! You can now use the bot.",
    },
}


def tr(key: str, lang: str, **kwargs) -> str:
    text = T[key].get(lang, T[key]["fa"])
    return text.format(**kwargs) if kwargs else text


def tag_label(field: str, lang: str) -> str:
    return TAG_FIELDS[field].get(lang, TAG_FIELDS[field]["fa"])


# ---------- ذخیره‌سازی تنظیمات کاربر ----------

def user_settings_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


def load_user_settings(user_id: int) -> dict:
    path = user_settings_path(user_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("lang", DEFAULT_LANG)
        return data
    return {"artist": None, "cover_path": None, "lang": DEFAULT_LANG}


def save_user_settings(user_id: int, settings: dict):
    user_settings_path(user_id).write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_lang(user_id: int) -> str:
    return load_user_settings(user_id).get("lang", DEFAULT_LANG)


# ---------- دستور تغییر زبان ----------

def language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ])


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    await update.message.reply_text(tr("choose_lang", lang), reply_markup=language_keyboard())


# ---------- دستورات پایه ----------

# ---------- بررسی عضویت اجباری در کانال ----------

async def is_member_of_channel(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(f"خطا در بررسی عضویت: {e}")
        # اگه بات نتونست بررسی کنه (مثلاً بات ادمین کانال نیست)، اجازه می‌ده کاربر رد شه
        return True


def join_keyboard(lang: str):
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr("join_button", lang), url=channel_url)],
        [InlineKeyboardButton(tr("check_join_button", lang), callback_data="check_join")],
    ])


async def enforce_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگه کاربر عضو نبود، پیام جوین رو می‌فرسته و False برمی‌گردونه."""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    if await is_member_of_channel(user_id, context):
        return True
    message = update.effective_message
    if message:
        await message.reply_text(tr("join_required", lang), reply_markup=join_keyboard(lang))
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await enforce_join(update, context):
        return

    if not user_settings_path(user_id).exists():
        settings = {"artist": None, "cover_path": None, "lang": DEFAULT_LANG}
        save_user_settings(user_id, settings)
        await update.message.reply_text(tr("choose_lang", DEFAULT_LANG), reply_markup=language_keyboard())
        return

    lang = get_lang(user_id)
    await update.message.reply_text(tr("start", lang))


async def set_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    if not context.args:
        await update.message.reply_text(tr("setartist_usage", lang))
        return
    settings = load_user_settings(user_id)
    settings["artist"] = " ".join(context.args)
    save_user_settings(user_id, settings)
    await update.message.reply_text(tr("artist_saved", lang, value=settings["artist"]))


async def set_cover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    message = update.effective_message
    photo = message.photo[-1] if message.photo else (
        message.reply_to_message.photo[-1] if message.reply_to_message and message.reply_to_message.photo else None
    )
    if not photo:
        await update.message.reply_text(tr("setcover_prompt", lang))
        return
    file = await context.bot.get_file(photo.file_id)
    cover_path = TEMP_DIR / f"cover_{user_id}.jpg"
    await file.download_to_drive(custom_path=str(cover_path))
    settings = load_user_settings(user_id)
    settings["cover_path"] = str(cover_path)
    save_user_settings(user_id, settings)
    await update.message.reply_text(tr("cover_saved", lang))


async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    settings = load_user_settings(user_id)
    artist = settings.get("artist") or tr("not_set", lang)
    cover = tr("has_it", lang) if settings.get("cover_path") and Path(settings["cover_path"]).exists() else tr("no_it", lang)
    await update.message.reply_text(tr("myinfo", lang, artist=artist, cover=cover))


# ---------- منوی اصلی ادیت (بر اساس زبان) ----------

def main_menu_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr("menu_tags", lang), callback_data="menu_tags")],
        [InlineKeyboardButton(tr("menu_cut", lang), callback_data="action_cut")],
        [InlineKeyboardButton(tr("menu_bitrate", lang), callback_data="menu_bitrate")],
        [InlineKeyboardButton(tr("menu_volume", lang), callback_data="menu_volume")],
        [InlineKeyboardButton(tr("menu_8d", lang), callback_data="action_8d")],
        [InlineKeyboardButton(tr("menu_voice", lang), callback_data="action_voice")],
        [InlineKeyboardButton(tr("menu_default", lang), callback_data="action_apply_default")],
        [InlineKeyboardButton(tr("menu_caption_template", lang), callback_data="menu_caption_template")],
        [InlineKeyboardButton(tr("menu_demo", lang), callback_data="action_demo")],
        [InlineKeyboardButton(tr("menu_finish", lang), callback_data="action_finish")],
    ])


def tags_menu_keyboard(lang: str):
    rows, row = [], []
    for key in TAG_FIELDS:
        row.append(InlineKeyboardButton(tag_label(key, lang), callback_data=f"tag_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(tr("menu_picture", lang), callback_data="tag_picture")])
    rows.append([InlineKeyboardButton(tr("menu_remove_all", lang), callback_data="tag_remove_all")])
    rows.append([InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def bitrate_keyboard(lang: str):
    presets = [128, 192, 256, 320]
    row = [InlineKeyboardButton(f"{b} kbps", callback_data=f"bitrate_{b}") for b in presets]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")]])


def genre_keyboard(lang: str, selected: set):
    rows, row = [], []
    for key, info in GENRE_LIST.items():
        label = info.get(lang, info["fa"])
        mark = "✅ " if key in selected else ""
        row.append(InlineKeyboardButton(f"{mark}{info['emoji']} {label}", callback_data=f"genre_toggle_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(tr("genre_done_btn", lang), callback_data="genre_done")])
    rows.append([InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def slogan_keyboard(lang: str, genre_key: str):
    rows = []
    slogans = SLOGANS.get(genre_key, SLOGANS["pop"])
    for idx, slogan in enumerate(slogans):
        text = slogan.get(lang, slogan["fa"])
        rows.append([InlineKeyboardButton(text, callback_data=f"slogan_{idx}")])
    rows.append([InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def year_keyboard(lang: str):
    current_year = datetime.now().year
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr("use_current_year", lang, current_year=current_year), callback_data=f"year_{current_year}")],
    ])


def volume_keyboard(lang: str):
    presets = [50, 75, 100, 125, 150, 200]
    rows = [[InlineKeyboardButton(f"{v}%", callback_data=f"volume_{v}") for v in presets[i:i+3]]
            for i in range(0, len(presets), 3)]
    rows.append([InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ---------- دریافت فایل صوتی ----------

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    audio = message.audio or message.document
    if audio is None:
        return

    if not await enforce_join(update, context):
        return

    user_id = update.effective_user.id
    lang = get_lang(user_id)
    file = await context.bot.get_file(audio.file_id)
    raw_path = TEMP_DIR / f"raw_{user_id}.mp3"
    await file.download_to_drive(custom_path=str(raw_path))

    work_path = TEMP_DIR / f"work_{user_id}.mp3"
    await message.reply_text(tr("receiving_file", lang))
    _run(["ffmpeg", "-y", "-i", str(raw_path), "-b:a", "320k", str(work_path)])
    raw_path.unlink(missing_ok=True)

    context.user_data["work_path"] = str(work_path)
    context.user_data["caption"] = ""
    context.user_data["awaiting"] = None

    await message.reply_text(tr("file_ready", lang), reply_markup=main_menu_keyboard(lang))


# ---------- روتر دکمه‌ها ----------

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    lang = get_lang(user_id)

    if data.startswith("lang_"):
        new_lang = data.replace("lang_", "")
        settings = load_user_settings(user_id)
        settings["lang"] = new_lang
        save_user_settings(user_id, settings)
        await query.edit_message_text(tr("lang_set", new_lang))
        await context.bot.send_message(chat_id=update.effective_chat.id, text=tr("start", new_lang))
        return

    if data == "check_join":
        if await is_member_of_channel(user_id, context):
            await query.edit_message_text(tr("join_confirmed", lang))
        else:
            await query.answer(tr("still_not_joined", lang), show_alert=True)
        return

    if "work_path" not in context.user_data and data not in ("back_main",):
        await query.edit_message_text(tr("need_file", lang))
        return

    if data == "back_main":
        await query.edit_message_text(tr("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "menu_tags":
        await query.edit_message_text(tr("which_tag", lang), reply_markup=tags_menu_keyboard(lang))

    elif data.startswith("tag_"):
        field = data.replace("tag_", "")
        if field == "remove_all":
            await remove_all_tags(context)
            await query.edit_message_text(tr("all_tags_removed", lang), reply_markup=main_menu_keyboard(lang))
        elif field == "picture":
            context.user_data["awaiting"] = "tag_picture"
            await query.edit_message_text(tr("send_new_cover", lang))
        else:
            context.user_data["awaiting"] = f"tag_{field}"
            label = tag_label(field, lang)
            await query.edit_message_text(tr("send_new_value", lang, label=label))

    elif data == "menu_bitrate":
        await query.edit_message_text(tr("choose_bitrate", lang), reply_markup=bitrate_keyboard(lang))

    elif data.startswith("bitrate_"):
        bitrate = data.replace("bitrate_", "")
        await query.edit_message_text(tr("applying_bitrate", lang))
        await run_ffmpeg_bitrate(context, bitrate)
        await query.edit_message_text(tr("bitrate_done", lang, bitrate=bitrate), reply_markup=main_menu_keyboard(lang))

    elif data == "menu_volume":
        await query.edit_message_text(tr("choose_volume", lang), reply_markup=volume_keyboard(lang))

    elif data.startswith("volume_"):
        percent = int(data.replace("volume_", ""))
        await query.edit_message_text(tr("applying_volume", lang))
        await run_ffmpeg_volume(context, percent)
        await query.edit_message_text(tr("volume_done", lang, percent=percent), reply_markup=main_menu_keyboard(lang))

    elif data == "action_cut":
        context.user_data["awaiting"] = "cut"
        await query.edit_message_text(tr("cut_prompt", lang))

    elif data == "action_8d":
        await query.edit_message_text(tr("applying_8d", lang))
        await run_ffmpeg_8d(context)
        await query.edit_message_text(tr("done_8d", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "action_voice":
        await query.edit_message_text(tr("converting_voice", lang))
        ogg_path = await run_ffmpeg_to_voice(context)
        await context.bot.send_voice(chat_id=update.effective_chat.id, voice=open(ogg_path, "rb"))
        await query.edit_message_text(tr("voice_sent", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "action_apply_default":
        settings = load_user_settings(user_id)
        await apply_default_tags(context, settings)
        await query.edit_message_text(tr("default_applied", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "menu_caption_template":
        context.user_data["selected_genres"] = set()
        await query.edit_message_text(tr("choose_genres", lang), reply_markup=genre_keyboard(lang, set()))

    elif data.startswith("genre_toggle_"):
        genre_key = data.replace("genre_toggle_", "")
        selected = context.user_data.setdefault("selected_genres", set())
        if genre_key in selected:
            selected.discard(genre_key)
        else:
            selected.add(genre_key)
        await query.edit_message_text(tr("choose_genres", lang), reply_markup=genre_keyboard(lang, selected))

    elif data == "genre_done":
        selected = context.user_data.get("selected_genres", set())
        if not selected:
            await query.answer(tr("no_genre_selected", lang), show_alert=True)
            return
        # اولین ژانر انتخاب‌شده به‌عنوان ژانر اصلی برای شعار در نظر گرفته می‌شه
        context.user_data["primary_genre"] = sorted(selected)[0]
        primary_genre = context.user_data["primary_genre"]
        await query.edit_message_text(tr("choose_slogan", lang), reply_markup=slogan_keyboard(lang, primary_genre))

    elif data.startswith("slogan_"):
        idx = int(data.replace("slogan_", ""))
        primary_genre = context.user_data.get("primary_genre", "pop")
        slogans = SLOGANS.get(primary_genre, SLOGANS["pop"])
        chosen = slogans[idx] if idx < len(slogans) else slogans[0]
        context.user_data["selected_slogan"] = chosen
        current_year = datetime.now().year
        await query.edit_message_text(
            tr("ask_year", lang, current_year=current_year),
            reply_markup=year_keyboard(lang),
        )
        context.user_data["awaiting"] = "caption_year"

    elif data.startswith("year_"):
        year = data.replace("year_", "")
        caption_text = build_caption_template(context, lang, year)
        context.user_data["caption"] = caption_text
        context.user_data["awaiting"] = None
        await query.edit_message_text(
            tr("caption_template_ready", lang) + "\n\n" + caption_text,
            reply_markup=main_menu_keyboard(lang),
        )

    elif data == "action_demo":
        await query.edit_message_text(tr("making_demo", lang))
        demo_path = await make_demo(context)
        await context.bot.send_audio(chat_id=update.effective_chat.id, audio=open(demo_path, "rb"),
                                      caption=tr("demo_caption", lang))
        await query.edit_message_text(tr("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "action_finish":
        work_path = Path(context.user_data["work_path"])
        caption = context.user_data.get("caption") or tr("final_caption_default", lang)
        await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=open(work_path, "rb"),
            caption=caption,
        )
        await query.edit_message_text(tr("final_sent", lang))


# ---------- دریافت متن (برای مقادیر تگ / برش / کپشن) ----------

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        return

    text = update.message.text.strip()

    if awaiting == "cut":
        try:
            start_s, end_s = map(int, text.replace(" ", "").split("-"))
        except Exception:
            await update.message.reply_text(tr("cut_bad_format", lang))
            return
        await update.message.reply_text(tr("cutting", lang))
        await run_ffmpeg_cut(context, start_s, end_s)
        context.user_data["awaiting"] = None
        await update.message.reply_text(tr("cut_done", lang), reply_markup=main_menu_keyboard(lang))
        return

    if awaiting.startswith("tag_"):
        field = awaiting.replace("tag_", "")
        set_single_tag(context, field, text)
        context.user_data["awaiting"] = None
        await update.message.reply_text(tr("value_saved", lang), reply_markup=main_menu_keyboard(lang))
        return

    if awaiting == "caption":
        context.user_data["caption"] = text
        context.user_data["awaiting"] = None
        await update.message.reply_text(tr("caption_saved", lang), reply_markup=main_menu_keyboard(lang))
        return


async def handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    if context.user_data.get("awaiting") != "tag_picture":
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    img_path = TEMP_DIR / f"newcover_{user_id}.jpg"
    await file.download_to_drive(custom_path=str(img_path))
    set_cover_tag(context, img_path)
    context.user_data["awaiting"] = None
    await update.message.reply_text(tr("new_cover_applied", lang), reply_markup=main_menu_keyboard(lang))


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
        frame_cls = TAG_FIELDS[field]["frame"]
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
    _run(["ffmpeg", "-y", "-i", str(path), "-af", "apulsator=hz=0.09", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_to_voice(context) -> Path:
    path = Path(context.user_data["work_path"])
    ogg_path = TEMP_DIR / f"voice_{path.stem}.ogg"
    _run(["ffmpeg", "-y", "-i", str(path), "-c:a", "libopus", "-b:a", "64k", str(ogg_path)])
    return ogg_path


def build_caption_template(context, lang: str, year: str) -> str:
    """کپشن نهایی رو بر اساس شعار انتخابی، سبک‌ها و سال می‌سازه."""
    selected = context.user_data.get("selected_genres", set())
    primary_genre = context.user_data.get("primary_genre", "pop")
    slogan = context.user_data.get("selected_slogan") or SLOGANS[primary_genre][0]
    emoji = GENRE_LIST.get(primary_genre, GENRE_LIST["pop"])["emoji"]
    slogan_text = slogan.get(lang, slogan["fa"])

    hashtags = " ".join(f"#{GENRE_LIST[g]['en'].replace(' ', '')}" for g in sorted(selected) if g in GENRE_LIST)
    hashtags += " #MeloLux"

    download_line = "دانلود فایل ۳۲۰kbps" if lang == "fa" else "Download 320kbps File"

    caption = (
        f"{emoji} *{slogan_text}*\n"
        f"📥 {download_line}\n\n"
        f"🆔 @MeloLux 🎧\n\n"
        f"{hashtags} #{year}"
    )
    return caption


async def make_demo(context) -> Path:
    path = Path(context.user_data["work_path"])
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
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("setartist", set_artist))
    app.add_handler(CommandHandler("setcover", set_cover))
    app.add_handler(CommandHandler("myinfo", my_info))

    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_input))

    logger.info("Bot is running... / بات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
