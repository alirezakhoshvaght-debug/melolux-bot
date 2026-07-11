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
import asyncio
from datetime import datetime
from pathlib import Path

from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, APIC, COMM, TPE2, TCOM, TPUB,
    TPOS, TBPM, TEXT, TCOP, TENC, USLT, ID3NoHeaderError,
)
from mutagen.mp3 import MP3

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton, InputMediaAudio,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
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
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID") or 0)  # آیدی عددی خودت؛ از @userinfobot بگیر

LANG_NAMES = {
    "fa": "🇮🇷 فارسی",
    "en": "🇬🇧 English",
    "ar": "🇸🇦 العربية",
    "tr": "🇹🇷 Türkçe",
    "ru": "🇷🇺 Русский",
}
# ================================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# ---------- تگ‌ها به هر دو زبان ----------
TAG_FIELDS = {
    "title":         {"fa": "🎶 عنوان",        "en": "🎶 Title",        "frame": TIT2},
    "artist":        {"fa": "👤 آرتیست",       "en": "👤 Artists",      "frame": TPE1},
    "album":         {"fa": "🗂 آلبوم",        "en": "🗂 Album",        "frame": TALB},
    "year":          {"fa": "📆 سال",          "en": "📆 Year",         "frame": TDRC},
    "genre":         {"fa": "🎙 ژانر",         "en": "🎙 Genre",        "frame": TCON},
    "track":         {"fa": "💿 شماره ترک",    "en": "💿 Track No.",    "frame": TRCK},
    "comment":       {"fa": "📝 کامنت",        "en": "📝 Comment",      "frame": None},
    "album_artist":  {"fa": "👥 آلبوم آرتیست", "en": "👥 Album Artist", "frame": TPE2},
    "composer":      {"fa": "👨‍💻 آهنگساز",     "en": "👨‍💻 Composer",    "frame": TCOM},
    "publisher":     {"fa": "👤 ناشر",         "en": "👤 Publisher",    "frame": TPUB},
    "disc":          {"fa": "📀 شماره دیسک",   "en": "📀 Disc No.",     "frame": TPOS},
    "bpm":           {"fa": "🥁 ضرب در دقیقه", "en": "🥁 BPM",          "frame": TBPM},
    "lyricist":      {"fa": "✍️ ترانه‌سرا",     "en": "✍️ Lyricist",     "frame": TEXT},
    "copyright":     {"fa": "©️ کپی‌رایت",      "en": "©️ Copyright",    "frame": TCOP},
    "encoded_by":    {"fa": "⚙️ کدگذاری‌شده توسط", "en": "⚙️ Encoded By", "frame": TENC},
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
    "jazz":         {"emoji": "🎺", "fa": "جاز",       "en": "Jazz",
                      "tag_fa": "ایمپرویزه، حس آزاد.", "tag_en": "Improvised, free feeling."},
    "classical":    {"emoji": "🎻", "fa": "کلاسیک",    "en": "Classical",
                      "tag_fa": "میراث موسیقی، حس ابدی.", "tag_en": "Musical heritage, timeless feel."},
    "lofi":         {"emoji": "☕", "fa": "لوفای",     "en": "Lo-fi",
                      "tag_fa": "صدای گرم، حس نوستالژیک.", "tag_en": "Warm sound, nostalgic feel."},
    "house":        {"emoji": "🕺", "fa": "هاوس",      "en": "House",
                      "tag_fa": "بیت رقص، انرژی شب.", "tag_en": "Dance beat, night energy."},
    "techno":       {"emoji": "🤖", "fa": "تکنو",      "en": "Techno",
                      "tag_fa": "ریتم ماشینی، انرژی خام.", "tag_en": "Machine rhythm, raw energy."},
    "metal":        {"emoji": "🤘", "fa": "متال",      "en": "Metal",
                      "tag_fa": "صدای سنگین، انرژی وحشی.", "tag_en": "Heavy sound, wild energy."},
    "reggae":       {"emoji": "🌴", "fa": "رگی",       "en": "Reggae",
                      "tag_fa": "ریتم گرمسیری، حس آزاد.", "tag_en": "Tropical rhythm, free feel."},
    "kpop":         {"emoji": "💜", "fa": "کی‌پاپ",    "en": "K-Pop",
                      "tag_fa": "انرژی رنگی، ریتم تازه.", "tag_en": "Colorful energy, fresh rhythm."},
    "drill":        {"emoji": "🩸", "fa": "دریل",      "en": "Drill",
                      "tag_fa": "بیت تاریک، حس خیابون.", "tag_en": "Dark beat, street feel."},
    "folk":         {"emoji": "🪗", "fa": "فولک",      "en": "Folk",
                      "tag_fa": "صدای سنتی، حس اصیل.", "tag_en": "Traditional sound, genuine feel."},
    "ambient":      {"emoji": "🌌", "fa": "امبیانت",   "en": "Ambient",
                      "tag_fa": "فضای بی‌کران، حس رویایی.", "tag_en": "Endless space, dreamy feel."},
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
    "jazz":         [{"fa": "ایمپرویزه، حس آزاد.", "en": "Improvised, free feeling."},
                      {"fa": "سویینگ نرم، احساس ظریف.", "en": "Smooth swing, delicate feel."},
                      {"fa": "صدای شب، حس خاص.", "en": "Nighttime sound, special feel."}],
    "classical":    [{"fa": "میراث موسیقی، حس ابدی.", "en": "Musical heritage, timeless feel."},
                      {"fa": "هارمونی ناب، احساس عمیق.", "en": "Pure harmony, deep feeling."},
                      {"fa": "صدای ارکستر، حس باشکوه.", "en": "Orchestral sound, majestic feel."}],
    "lofi":         [{"fa": "صدای گرم، حس نوستالژیک.", "en": "Warm sound, nostalgic feel."},
                      {"fa": "ریتم آروم، شب مطالعه.", "en": "Chill beat, study night."},
                      {"fa": "صدای خش‌دار، حس دنج.", "en": "Crackly sound, cozy feel."}],
    "house":        [{"fa": "بیت رقص، انرژی شب.", "en": "Dance beat, night energy."},
                      {"fa": "ریتم کلاب، حس آزاد.", "en": "Club rhythm, free feel."},
                      {"fa": "بیس گرم، انرژی رقص.", "en": "Warm bass, dance energy."}],
    "techno":       [{"fa": "ریتم ماشینی، انرژی خام.", "en": "Machine rhythm, raw energy."},
                      {"fa": "بیت تکراری، حس هیپنوتیزم.", "en": "Repetitive beat, hypnotic feel."},
                      {"fa": "صدای زیرزمینی، انرژی تاریک.", "en": "Underground sound, dark energy."}],
    "metal":        [{"fa": "صدای سنگین، انرژی وحشی.", "en": "Heavy sound, wild energy."},
                      {"fa": "ریف تیز، حس خشم.", "en": "Sharp riff, raging feel."},
                      {"fa": "طوفان صدا، انرژی خام.", "en": "Sound storm, raw energy."}],
    "reggae":       [{"fa": "ریتم گرمسیری، حس آزاد.", "en": "Tropical rhythm, free feel."},
                      {"fa": "بیت آفتابی، حس آروم.", "en": "Sunny beat, relaxed feel."},
                      {"fa": "صدای ساحلی، انرژی مثبت.", "en": "Beachside sound, positive energy."}],
    "kpop":         [{"fa": "انرژی رنگی، ریتم تازه.", "en": "Colorful energy, fresh rhythm."},
                      {"fa": "بیت پرانرژی، حس شاد.", "en": "High-energy beat, happy feel."},
                      {"fa": "صدای مدرن، انرژی جوان.", "en": "Modern sound, youthful energy."}],
    "drill":        [{"fa": "بیت تاریک، حس خیابون.", "en": "Dark beat, street feel."},
                      {"fa": "ریتم سرد، انرژی خام.", "en": "Cold rhythm, raw energy."},
                      {"fa": "بیس عمیق، حس تهدید.", "en": "Deep bass, ominous feel."}],
    "folk":         [{"fa": "صدای سنتی، حس اصیل.", "en": "Traditional sound, genuine feel."},
                      {"fa": "ملودی ریشه‌دار، حس صمیمی.", "en": "Rooted melody, intimate feel."},
                      {"fa": "داستان‌گویی، حس گرم.", "en": "Storytelling, warm feel."}],
    "ambient":      [{"fa": "فضای بی‌کران، حس رویایی.", "en": "Endless space, dreamy feel."},
                      {"fa": "صدای معلق، آرامش عمیق.", "en": "Floating sound, deep calm."},
                      {"fa": "لایه‌های نرم، حس مدیتیشن.", "en": "Soft layers, meditative feel."}],
}


# ---------- دیکشنری کامل متن‌ها ----------
T = {
    "choose_lang": {
        "fa": "🌐 لطفاً زبان مورد نظرت رو انتخاب کن:",
        "en": "🌐 Please choose your language:",
        "ar": "🌐 الرجاء اختيار لغتك:",
        "tr": "🌐 Lütfen dilinizi seçin:",
        "ru": "🌐 Пожалуйста, выберите язык:",
    },
    "lang_set": {
        "fa": "✅ زبان روی فارسی تنظیم شد.",
        "en": "✅ Language set to English.",
        "ar": "✅ تم ضبط اللغة على العربية.",
        "tr": "✅ Dil Türkçe olarak ayarlandı.",
        "ru": "✅ Язык установлен на русский.",
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
        "ar": (
            "مرحباً! 🎵 بوت تحرير الموسيقى ملولوكس في خدمتك.\n\n"
            "أولاً احفظ إعداداتك الافتراضية:\n"
            "• /setartist <الاسم> — اسم القناة/الفنان الافتراضي\n"
            "• أرسل صورة ورد عليها بـ /setcover — الغلاف الافتراضي\n"
            "• /myinfo — عرض الإعدادات الحالية\n"
            "• /language — تغيير لغة البوت\n\n"
            "بعدها أرسل ملف MP3 لفتح قائمة التحرير 🎛"
        ),
        "tr": (
            "Merhaba! 🎵 Melolux Müzik Düzenleme Botu hizmetinizde.\n\n"
            "Önce varsayılan ayarlarını kaydet:\n"
            "• /setartist <isim> — varsayılan kanal/sanatçı adı\n"
            "• Bir fotoğraf gönder ve /setcover ile yanıtla — varsayılan kapak\n"
            "• /myinfo — mevcut ayarları görüntüle\n"
            "• /language — bot dilini değiştir\n\n"
            "Sonra düzenleme menüsünü açmak için bir MP3 dosyası gönder 🎛"
        ),
        "ru": (
            "Привет! 🎵 Бот редактирования музыки Melolux к вашим услугам.\n\n"
            "Сначала сохрани настройки по умолчанию:\n"
            "• /setartist <имя> — имя канала/исполнителя по умолчанию\n"
            "• Отправь фото и ответь на него /setcover — обложка по умолчанию\n"
            "• /myinfo — посмотреть текущие настройки\n"
            "• /language — сменить язык бота\n\n"
            "Затем отправь MP3-файл, чтобы открыть меню редактирования 🎛"
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

    "menu_tags": {"fa": "✏️ ادیت تگ‌ها", "en": "✏️ Edit Tags", "ar": "✏️ تعديل الوسوم", "tr": "✏️ Etiketleri Düzenle", "ru": "✏️ Изменить теги"},
    "menu_cut": {"fa": "✂️ برش (Cut)", "en": "✂️ Cut", "ar": "✂️ قص", "tr": "✂️ Kes", "ru": "✂️ Обрезать"},
    "menu_bitrate": {"fa": "🎚 تنظیم بیت‌ریت", "en": "🎚 Set Bitrate", "ar": "🎚 ضبط معدل البت", "tr": "🎚 Bit Hızı Ayarla", "ru": "🎚 Битрейт"},
    "menu_volume": {"fa": "🔊 ولوم", "en": "🔊 Volume", "ar": "🔊 مستوى الصوت", "tr": "🔊 Ses Seviyesi", "ru": "🔊 Громкость"},
    "menu_8d": {"fa": "🎧 افکت 8D (Paning)", "en": "🎧 8D (Paning)", "ar": "🎧 تأثير 8D", "tr": "🎧 8D Efekti", "ru": "🎧 Эффект 8D"},
    "menu_voice": {"fa": "🎤 تبدیل به ویس", "en": "🎤 Convert to Voice", "ar": "🎤 تحويل إلى رسالة صوتية", "tr": "🎤 Sesli Mesaja Çevir", "ru": "🎤 В голосовое"},
    "menu_default": {"fa": "📌 اعمال تنظیمات پیش‌فرض", "en": "📌 Apply Default Settings", "ar": "📌 تطبيق الإعدادات الافتراضية", "tr": "📌 Varsayılanı Uygula", "ru": "📌 Применить настройки"},
    "menu_mixed_voice": {"fa": "🎚 میکس صدا", "en": "🎚 Mixed voice"},
    "menu_effects": {"fa": "🪄 افکت‌ها", "en": "🪄 Effects"},
    "choose_effect": {"fa": "یکی از افکت‌ها رو انتخاب کن:", "en": "Choose an effect:"},
    "applying_effect": {"fa": "⏳ در حال اعمال افکت...", "en": "⏳ Applying effect..."},
    "effect_done": {"fa": "✅ افکت اعمال شد.", "en": "✅ Effect applied."},
    "applying_mixed_voice": {"fa": "⏳ در حال میکس صدا...", "en": "⏳ Mixing voice..."},
    "mixed_voice_done": {"fa": "✅ میکس صدا اعمال شد.", "en": "✅ Mixed voice applied."},
    "change_caption_prompt": {"fa": "کپشن جدید رو بفرست:", "en": "Send the new caption:"},
    "fx_bass_boost": {"fa": "🔊 بیس بوستر", "en": "🔊 Bass Boost"},
    "fx_nightcore": {"fa": "🌙 نایت‌کور", "en": "🌙 Nightcore"},
    "fx_echo": {"fa": "🌊 اکو", "en": "🌊 Echo"},
    "fx_robotic": {"fa": "🤖 رباتیک", "en": "🤖 Robotic"},
    "fx_slowed": {"fa": "🐌 آهسته", "en": "🐌 Slowed"},
    "please_select_option": {"fa": "لطفاً یه گزینه انتخاب کن 👇", "en": "Please select an option 👇"},
    "choose_effect": {"fa": "کدوم افکت رو می‌خوای؟", "en": "Which effect do you want?"},
    "effect_bass": {"fa": "🔊 بیس بوست", "en": "🔊 Bass Boost"},
    "effect_nightcore": {"fa": "⚡ نایت‌کور", "en": "⚡ Nightcore"},
    "effect_slowedreverb": {"fa": "🌙 اسلوود + ریوربی", "en": "🌙 Slowed + Reverb"},
    "effect_deep": {"fa": "🕳 صدای بم", "en": "🕳 Deep Voice"},
    "effect_chipmunk": {"fa": "🐿 صدای نازک", "en": "🐿 Chipmunk"},
    "applying_effect": {"fa": "⏳ در حال اعمال افکت...", "en": "⏳ Applying effect..."},
    "effect_done": {"fa": "✅ افکت اعمال شد.", "en": "✅ Effect applied."},
    "applying_mixed_voice": {"fa": "⏳ در حال میکس صدا...", "en": "⏳ Mixing voice..."},
    "mixed_voice_done": {"fa": "✅ میکس صدا اعمال شد.", "en": "✅ Mixed voice applied."},
    "menu_demo": {"fa": "🎬 دموی ۴۵ ثانیه‌ای", "en": "🎬 45s Demo", "ar": "🎬 عرض ٤٥ ثانية", "tr": "🎬 45sn Demo", "ru": "🎬 Демо 45с"},
    "menu_finish": {"fa": "✅ ارسال فایل نهایی", "en": "✅ Send Final File", "ar": "✅ إرسال الملف النهائي", "tr": "✅ Son Dosyayı Gönder", "ru": "✅ Отправить файл"},
    "menu_picture": {"fa": "🖼 کاور", "en": "🖼 Picture", "ar": "🖼 الصورة", "tr": "🖼 Kapak", "ru": "🖼 Обложка"},
    "menu_remove_all": {"fa": "🗑 پاک کردن همه‌ی تگ‌ها", "en": "🗑 Remove All Tags", "ar": "🗑 حذف كل الوسوم", "tr": "🗑 Tüm Etiketleri Sil", "ru": "🗑 Удалить все теги"},
    "menu_filename": {"fa": "🏷 اسم فایل", "en": "🏷 File Name"},
    "menu_lyrics": {"fa": "📜 متن آهنگ", "en": "📜 Lyrics"},
    "menu_show_lyrics": {"fa": "👁 نمایش متن آهنگ", "en": "👁 Show Lyrics"},
    "menu_save_tags": {"fa": "💾 ذخیره", "en": "💾 Save"},
    "send_new_filename": {"fa": "اسم جدید فایل رو بفرست (بدون پسوند):", "en": "Send the new file name (without extension):"},
    "filename_saved": {"fa": "✅ اسم فایل ذخیره شد.", "en": "✅ File name saved."},
    "send_new_lyrics": {"fa": "متن آهنگ رو بفرست:", "en": "Send the lyrics:"},
    "lyrics_saved": {"fa": "✅ متن آهنگ ذخیره شد.", "en": "✅ Lyrics saved."},
    "no_lyrics": {"fa": "این فایل هنوز متن آهنگ نداره.", "en": "This file has no lyrics yet."},
    "tags_saved_final": {"fa": "💾 همه‌ی تگ‌ها ذخیره شدن.", "en": "💾 All tags saved."},
    "menu_back": {"fa": "🔙 بازگشت", "en": "🔙 Back", "ar": "🔙 رجوع", "tr": "🔙 Geri", "ru": "🔙 Назад"},

    "need_file": {"fa": "اول یه فایل MP3 بفرست.", "en": "Send an MP3 file first."},
    "main_menu_title": {"fa": "لطفاً یک گزینه رو انتخاب کن 👇", "en": "Please select an option 👇"},
    "which_tag": {"fa": "کدوم تگ رو می‌خوای ادیت کنی؟", "en": "Which tag do you want to edit?"},
    "select_option": {
        "fa": "لطفاً یکی از گزینه‌ها رو انتخاب کن 👇",
        "en": "Please select an option 👇",
    },
    "all_tags_removed": {"fa": "✅ همه‌ی تگ‌ها پاک شد.", "en": "✅ All tags removed."},
    "send_new_cover": {"fa": "عکس کاور جدید رو بفرست:", "en": "Send the new cover photo:"},
    "send_new_value": {"fa": "{label} جدید رو بفرست:", "en": "Send the new {label}:"},
    "field_add": {"fa": "➕ افزودن / تغییر", "en": "➕ Add / Edit"},
    "field_copy": {"fa": "📋 کپی مقدار", "en": "📋 Copy Value"},
    "field_delete": {"fa": "🗑 حذف", "en": "🗑 Delete"},
    "field_cancel": {"fa": "❌ لغو", "en": "❌ Cancel"},
    "current_value_label": {"fa": "مقدار فعلی", "en": "Current value"},
    "no_value_set": {"fa": "— ثبت نشده —", "en": "— not set —"},
    "value_deleted": {"fa": "✅ حذف شد.", "en": "✅ Deleted."},
    "copy_value_caption": {"fa": "مقدار کپی‌شده:", "en": "Copied value:"},
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
    "making_demo": {"fa": "⏳ در حال ساخت دمو...", "en": "⏳ Creating demo..."},
    "demo_caption": {"fa": "🎬 دموی {sec} ثانیه‌ای", "en": "🎬 {sec}-second demo"},
    "choose_demo_duration": {
        "fa": "مدت‌زمان دمو رو انتخاب کن:",
        "en": "Choose the demo duration:",
    },
    "demo_manual_option": {"fa": "✍️ دستی (ثانیه)", "en": "✍️ Manual (seconds)"},
    "demo_manual_prompt": {
        "fa": "تعداد ثانیه‌ی موردنظر رو بفرست (مثلاً 20):",
        "en": "Send the desired number of seconds (e.g. 20):",
    },
    "demo_bad_number": {"fa": "❌ یه عدد معتبر بفرست.", "en": "❌ Please send a valid number."},
    "choose_bitrate_panel": {
        "fa": "بیت‌ریت رو از پایین صفحه انتخاب کن 👇",
        "en": "Choose bitrate from the panel below 👇",
    },
    "choose_volume_panel": {
        "fa": "درصد ولوم رو از پایین صفحه انتخاب کن 👇",
        "en": "Choose volume percentage from the panel below 👇",
    },
    "panel_closed": {"fa": "✅ انجام شد.", "en": "✅ Done."},
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
        "fa": "🎧 {name}\nفایل آماده‌ست! از منوی زیر انتخاب کن:",
        "en": "🎧 {name}\nFile ready! Choose from the menu below:",
        "ar": "🎧 {name}\nالملف جاهز! اختر من القائمة أدناه:",
        "tr": "🎧 {name}\nDosya hazır! Aşağıdaki menüden seç:",
        "ru": "🎧 {name}\nФайл готов! Выберите из меню ниже:",
    },
    "menu_caption_template": {"fa": "✏️ تغییر کپشن", "en": "✏️ Change Caption"},
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
    "title_preview": {
        "fa": "🎵 عنوان تنظیم شد:\n\n{title}\n\nروی دکمه‌ی زیر بزن تا کپی بشه.",
        "en": "🎵 Title set:\n\n{title}\n\nTap the button below to copy it.",
    },
    "copy_title_button": {"fa": "📋 کپی عنوان", "en": "📋 Copy Title"},
}


def tr(key: str, lang: str, **kwargs) -> str:
    entry = T[key]
    text = entry.get(lang) or entry.get("en") or entry.get("fa")
    return text.format(**kwargs) if kwargs else text


def tag_label(field: str, lang: str) -> str:
    if field == "filename":
        return tr("menu_filename", lang)
    if field == "lyrics":
        return tr("menu_lyrics", lang)
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


# ---------- ثبت و شمارش ممبرها ----------

MEMBERS_FILE = DATA_DIR / "members.json"


def register_member(user) -> bool:
    """کاربر رو توی لیست ممبرها ثبت می‌کنه. اگه کاربر جدید بود True برمی‌گردونه."""
    members = {}
    if MEMBERS_FILE.exists():
        try:
            members = json.loads(MEMBERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            members = {}

    uid = str(user.id)
    is_new = uid not in members
    members[uid] = {
        "username": user.username or "",
        "first_name": user.first_name or "",
        "joined_at": members.get(uid, {}).get("joined_at") or datetime.now().isoformat(),
    }
    MEMBERS_FILE.write_text(json.dumps(members, ensure_ascii=False, indent=2), encoding="utf-8")
    return is_new


def get_all_members() -> dict:
    if MEMBERS_FILE.exists():
        try:
            return json.loads(MEMBERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_member_count() -> int:
    return len(get_all_members())


async def sync_bot_description(context: ContextTypes.DEFAULT_TYPE):
    """تعداد کاربرا رو توی توضیحات کوتاه بات آپدیت می‌کنه تا بالای صفحه‌ی بات دیده بشه."""
    try:
        count = get_member_count()
        await context.bot.set_my_short_description(
            short_description=f"🎵 بات ادیت موزیک ملولوکس | 👥 {count} کاربر"
        )
    except Exception as e:
        logger.warning(f"خطا در آپدیت توضیحات بات: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور مخصوص ادمین برای دیدن تعداد و لیست ممبرها با لینک مستقیم به اکانتشون."""
    user_id = update.effective_user.id
    if ADMIN_USER_ID == 0 or user_id != ADMIN_USER_ID:
        return  # فقط ادمین می‌تونه این دستور رو ببینه

    members = get_all_members()
    count = len(members)

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = [f"👥 <b>تعداد کل کاربران بات: {count}</b>\n"]
    for uid, info in sorted(members.items(), key=lambda x: x[1].get("joined_at", ""), reverse=True)[:50]:
        name = esc(info.get("first_name") or "کاربر")
        username = info.get("username")
        uname_part = f" (@{esc(username)})" if username else ""
        # لینک قابل‌کلیک به اکانت کاربر، حتی اگه یوزرنیم نداشته باشه
        lines.append(f'• <a href="tg://user?id={uid}">{name}</a>{uname_part} — ID: <code>{uid}</code>')

    if count > 50:
        lines.append(f"\n… و {count - 50} کاربر دیگه")

    text = "\n".join(lines)
    # تلگرام محدودیت طول پیام داره؛ در صورت طولانی بودن، تکه‌تکه بفرست
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000], parse_mode="HTML")


# ---------- دستور تغییر زبان ----------

def language_keyboard():
    rows, row = [], []
    for code, label in LANG_NAMES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"lang_{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


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

    is_new_member = register_member(update.effective_user)
    if is_new_member:
        await sync_bot_description(context)

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
        [InlineKeyboardButton("📝 Edit tags" if lang != "fa" else "📝 ادیت تگ‌ها", callback_data="menu_tags")],
        [InlineKeyboardButton("✂️ Cut" if lang != "fa" else "✂️ برش", callback_data="action_cut")],
        [InlineKeyboardButton("🎙 Convert to voice" if lang != "fa" else "🎙 تبدیل به ویس", callback_data="action_voice")],
        [InlineKeyboardButton("🎧 Mixed voice" if lang != "fa" else "🎧 میکس صدا", callback_data="action_mixed_voice")],
        [InlineKeyboardButton("🌀 8D (Paning)" if lang != "fa" else "🌀 افکت 8D", callback_data="action_8d")],
        [InlineKeyboardButton("⚙️ Set bitrate" if lang != "fa" else "⚙️ تنظیم بیت‌ریت", callback_data="menu_bitrate")],
        [InlineKeyboardButton("🔊 Volume" if lang != "fa" else "🔊 ولوم", callback_data="menu_volume")],
        [InlineKeyboardButton("✨ Effects" if lang != "fa" else "✨ افکت‌ها", callback_data="menu_effects")],
        [InlineKeyboardButton("✍️ Change caption" if lang != "fa" else "✍️ تغییر کپشن", callback_data="action_change_caption")],
        [InlineKeyboardButton("🎬 Demo" if lang != "fa" else "🎬 دمو", callback_data="action_demo")],
        [InlineKeyboardButton("🏷 Caption Template" if lang != "fa" else "🏷 قالب کپشن", callback_data="menu_caption_template")],
    ])


def field_detail_keyboard(lang: str, field: str, has_value: bool):
    rows = [
        [InlineKeyboardButton(tr("field_add", lang), callback_data=f"field_edit_{field}")],
    ]
    row2 = []
    if has_value:
        row2.append(InlineKeyboardButton(tr("field_copy", lang), callback_data=f"field_copy_{field}"))
        row2.append(InlineKeyboardButton(tr("field_delete", lang), callback_data=f"field_delete_{field}"))
    if row2:
        rows.append(row2)
    rows.append([InlineKeyboardButton(tr("field_cancel", lang), callback_data="field_cancel")])
    return InlineKeyboardMarkup(rows)


def tags_menu_keyboard(lang: str, edited: set = None):
    edited = edited or set()

    def m(key):
        return "✅ " if key in edited else ""

    rows = [
        [
            InlineKeyboardButton(m("filename") + tr("menu_filename", lang), callback_data="tag_filename"),
            InlineKeyboardButton(m("title") + tag_label("title", lang), callback_data="tag_title"),
        ],
        [
            InlineKeyboardButton(m("artist") + tag_label("artist", lang), callback_data="tag_artist"),
            InlineKeyboardButton(m("picture") + tr("menu_picture", lang), callback_data="tag_picture"),
        ],
        [
            InlineKeyboardButton(m("album") + tag_label("album", lang), callback_data="tag_album"),
            InlineKeyboardButton(m("year") + tag_label("year", lang), callback_data="tag_year"),
        ],
        [
            InlineKeyboardButton(m("track") + tag_label("track", lang), callback_data="tag_track"),
            InlineKeyboardButton(m("genre") + tag_label("genre", lang), callback_data="tag_genre"),
        ],
        [
            InlineKeyboardButton(m("lyrics") + tr("menu_lyrics", lang), callback_data="tag_lyrics"),
            InlineKeyboardButton(m("comment") + tag_label("comment", lang), callback_data="tag_comment"),
        ],
        [
            InlineKeyboardButton(m("album_artist") + tag_label("album_artist", lang), callback_data="tag_album_artist"),
            InlineKeyboardButton(m("composer") + tag_label("composer", lang), callback_data="tag_composer"),
        ],
        [
            InlineKeyboardButton(m("disc") + tag_label("disc", lang), callback_data="tag_disc"),
            InlineKeyboardButton(m("publisher") + tag_label("publisher", lang), callback_data="tag_publisher"),
        ],
        [
            InlineKeyboardButton(tr("menu_show_lyrics", lang), callback_data="show_lyrics"),
            InlineKeyboardButton(tr("menu_remove_all", lang), callback_data="tag_remove_all"),
        ],
        [InlineKeyboardButton(tr("menu_save_tags", lang), callback_data="tags_save")],
        [InlineKeyboardButton(tr("menu_default", lang), callback_data="action_apply_default")],
        [InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(rows)


def bottom_panel(options: list, columns: int = 4) -> ReplyKeyboardMarkup:
    """کیبورد پایین صفحه با دکمه‌های مستطیلی، مستقل از پیام اصلی."""
    rows = [options[i:i + columns] for i in range(0, len(options), columns)]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def bitrate_keyboard(lang: str):
    presets = [64, 96, 128, 160, 192, 224, 256, 320]
    rows = [[InlineKeyboardButton(f"{b} kbps", callback_data=f"bitrate_{b}") for b in presets[i:i+4]]
            for i in range(0, len(presets), 4)]
    rows.append([InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


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
    presets = [25, 50, 75, 100, 125, 150, 175, 200]
    rows = [[InlineKeyboardButton(f"{v}%", callback_data=f"volume_{v}") for v in presets[i:i+4]]
            for i in range(0, len(presets), 4)]
    rows.append([InlineKeyboardButton(tr("menu_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ---------- دریافت فایل صوتی ----------

async def render(query, text, reply_markup=None):
    """پیام رو ویرایش می‌کنه؛ اگه پیام یه فایل صوتی/ویس باشه، کپشنش رو عوض می‌کنه، وگرنه متن."""
    msg = query.message
    if msg and (msg.audio or msg.voice):
        await query.edit_message_caption(caption=text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text, reply_markup=reply_markup)


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
    work_path = TEMP_DIR / f"work_{user_id}.mp3"

    # فایل مستقیم و بدون تبدیل کیفیت ذخیره می‌شه (سرعت بالا)؛
    # کیفیت رو کاربر بعداً از منوی «تنظیم بیت‌ریت» خودش انتخاب می‌کنه
    await file.download_to_drive(custom_path=str(work_path))

    context.user_data["work_path"] = str(work_path)
    context.user_data["caption"] = ""
    context.user_data["awaiting"] = None
    context.user_data["edited_tags"] = set()

    # اگه فایل از قبل کاور داشته باشه، استخراجش می‌کنیم تا هم به‌عنوان تامبنیل نشون داده بشه هم بعداً قابل جایگزینی باشه
    existing_cover_path = extract_existing_cover(work_path, user_id)
    if existing_cover_path:
        context.user_data["cover_image_path"] = str(existing_cover_path)
    else:
        context.user_data.pop("cover_image_path", None)

    title, artist = get_title_artist(work_path)
    original_name = getattr(audio, "file_name", None)
    if original_name and original_name.lower().endswith((".mp3", ".m4a", ".wav", ".flac", ".ogg")):
        original_name = re.sub(r"\.[^.]+$", "", original_name)  # حذف پسوند اصلی
    display_name = title or original_name or "Melolux Track"
    safe_name = re.sub(r'[^\w\-. ]', '', display_name).strip() or "Melolux Track"
    context.user_data["display_filename"] = safe_name

    caption_text = tr("select_option", lang)
    audio_file = open(work_path, "rb")
    thumb_file = open(existing_cover_path, "rb") if existing_cover_path else None
    try:
        sent = await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=audio_file,
            filename=f"{safe_name}.mp3",
            title=title,
            performer=artist,
            thumbnail=thumb_file,
            caption=caption_text,
            reply_markup=main_menu_keyboard(lang),
        )
    finally:
        audio_file.close()
        if thumb_file:
            thumb_file.close()
    context.user_data["menu_chat_id"] = sent.chat_id
    context.user_data["menu_message_id"] = sent.message_id


async def update_menu_message(context, text, keyboard):
    """کپشن و منوی زیر فایل صوتی اصلی رو ویرایش می‌کنه بدون فرستادن پیام جدید."""
    chat_id = context.user_data.get("menu_chat_id")
    message_id = context.user_data.get("menu_message_id")
    if not chat_id or not message_id:
        return
    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=text, reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"خطا در آپدیت پیام منو: {e}")


async def refresh_audio_media(context, text, keyboard):
    """فایل صوتی پیام رو دوباره آپلود می‌کنه (با کاور/تگ‌های جدید) تا تصویر کاور واقعاً توی تلگرام آپدیت بشه."""
    chat_id = context.user_data.get("menu_chat_id")
    message_id = context.user_data.get("menu_message_id")
    if not chat_id or not message_id:
        return
    path = Path(context.user_data["work_path"])
    title, artist = get_title_artist(path)
    display_name = title or context.user_data.get("display_filename") or "Melolux Track"
    safe_name = re.sub(r'[^\w\-. ]', '', display_name).strip() or "Melolux Track"
    thumb_path = context.user_data.get("cover_image_path")
    audio_file = open(path, "rb")
    thumb_file = open(thumb_path, "rb") if thumb_path and Path(thumb_path).exists() else None
    try:
        media = InputMediaAudio(
            media=audio_file,
            thumbnail=thumb_file,
            title=title,
            performer=artist,
            caption=text,
            filename=f"{safe_name}.mp3",
        )
        await context.bot.edit_message_media(chat_id=chat_id, message_id=message_id, media=media)
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"خطا در آپدیت فایل و کاور پیام: {e}")
        # حداقل کپشن رو آپدیت کن اگه آپدیت فایل شکست خورد
        await update_menu_message(context, text, keyboard)
    finally:
        audio_file.close()
        if thumb_file:
            thumb_file.close()


# ---------- روتر دکمه‌ها ----------

async def send_final_file(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """فایل نهایی رو می‌فرسته؛ هم از «ارسال فایل نهایی» و هم از «سیو» در ادیت تگ‌ها صدا زده می‌شه."""
    work_path = Path(context.user_data["work_path"])
    caption = context.user_data.get("caption") or tr("final_caption_default", lang)
    title, artist = get_title_artist(work_path)
    custom_filename = context.user_data.get("custom_filename")
    if custom_filename:
        safe_name = re.sub(r'[^\w\-. ]', '', custom_filename)
    elif title:
        safe_name = re.sub(r'[^\w\-. ]', '', title)
    else:
        safe_name = "melolux_track"
    audio_file = open(work_path, "rb")
    try:
        await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=audio_file,
            filename=f"{safe_name}.mp3",
            title=title,
            performer=artist,
            caption=caption,
        )
    finally:
        audio_file.close()


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
        await render(query, tr("lang_set", new_lang))
        await context.bot.send_message(chat_id=update.effective_chat.id, text=tr("start", new_lang))
        return

    if data == "check_join":
        if await is_member_of_channel(user_id, context):
            await render(query, tr("join_confirmed", lang))
        else:
            await query.answer(tr("still_not_joined", lang), show_alert=True)
        return

    if "work_path" not in context.user_data and data not in ("back_main",):
        await render(query, tr("need_file", lang))
        return

    if data == "back_main":
        await render(query, tr("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "menu_tags":
        edited = context.user_data.setdefault("edited_tags", set())
        meta = build_metadata_caption(context, Path(context.user_data["work_path"]), lang)
        await render(query, f'{tr("which_tag", lang)}\n\n{meta}', reply_markup=tags_menu_keyboard(lang, edited))

    elif data.startswith("tag_"):
        field = data.replace("tag_", "")
        if field == "remove_all":
            await remove_all_tags(context)
            context.user_data["edited_tags"] = set()
            meta = build_metadata_caption(context, Path(context.user_data["work_path"]), lang)
            await render(query, f'{tr("all_tags_removed", lang)}\n\n{meta}', reply_markup=tags_menu_keyboard(lang, set()))
        elif field == "picture":
            context.user_data["awaiting"] = "tag_picture"
            await render(query, tr("send_new_cover", lang))
        else:
            current_value = get_tag_value(context, field)
            label = tag_label(field, lang)
            value_display = current_value if current_value else tr("no_value_set", lang)
            text = f"{label}\n\n{tr('current_value_label', lang)}: {value_display}"
            await render(query, text, reply_markup=field_detail_keyboard(lang, field, bool(current_value)))

    elif data == "field_cancel":
        edited = context.user_data.setdefault("edited_tags", set())
        meta = build_metadata_caption(context, Path(context.user_data["work_path"]), lang)
        await render(query, f'{tr("which_tag", lang)}\n\n{meta}', reply_markup=tags_menu_keyboard(lang, edited))

    elif data.startswith("field_edit_"):
        field = data.replace("field_edit_", "")
        context.user_data["awaiting"] = f"tag_{field}"
        if field == "filename":
            prompt_text = tr("send_new_filename", lang)
        elif field == "lyrics":
            prompt_text = tr("send_new_lyrics", lang)
        else:
            label = tag_label(field, lang)
            prompt_text = tr("send_new_value", lang, label=label)
        await render(query, prompt_text)

    elif data.startswith("field_delete_"):
        field = data.replace("field_delete_", "")
        delete_single_tag(context, field)
        edited = context.user_data.setdefault("edited_tags", set())
        edited.discard(field)
        meta = build_metadata_caption(context, Path(context.user_data["work_path"]), lang)
        await render(query, f'{tr("value_deleted", lang)}\n\n{meta}', reply_markup=tags_menu_keyboard(lang, edited))

    elif data.startswith("field_copy_"):
        field = data.replace("field_copy_", "")
        current_value = get_tag_value(context, field) or ""
        try:
            copy_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(tr("copy_title_button", lang), copy_text=CopyTextButton(current_value))]]
            )
        except Exception:
            copy_keyboard = None
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{tr('copy_value_caption', lang)}\n{current_value}",
            reply_markup=copy_keyboard,
        )

    elif data == "menu_bitrate":
        await render(query, tr("choose_bitrate_panel", lang))
        presets = [64, 96, 128, 160, 192, 224, 256, 320]
        options = [f"{b} kbps" for b in presets]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=tr("choose_bitrate", lang),
            reply_markup=bottom_panel(options, columns=4),
        )
        context.user_data["awaiting"] = "reply_bitrate"

    elif data == "menu_volume":
        await render(query, tr("choose_volume_panel", lang))
        presets = [25, 50, 75, 100, 125, 150, 175, 200]
        options = [f"{v}%" for v in presets]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=tr("choose_volume", lang),
            reply_markup=bottom_panel(options, columns=4),
        )
        context.user_data["awaiting"] = "reply_volume"

    elif data == "action_cut":
        context.user_data["awaiting"] = "cut"
        await render(query, tr("cut_prompt", lang))

    elif data == "action_8d":
        await render(query, tr("applying_8d", lang))
        await run_ffmpeg_8d(context)
        await render(query, tr("done_8d", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "action_mixed_voice":
        await render(query, tr("applying_mixed_voice", lang))
        await run_ffmpeg_mixed_voice(context)
        await render(query, tr("mixed_voice_done", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "menu_effects":
        await render(query, tr("choose_effect", lang))
        fx_labels = ["fx_bass_boost", "fx_nightcore", "fx_echo", "fx_robotic", "fx_slowed"]
        options = [tr(k, lang) for k in fx_labels]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=tr("choose_effect", lang),
            reply_markup=bottom_panel(options, columns=3),
        )
        context.user_data["awaiting"] = "reply_effect"

    elif data == "action_change_caption":
        context.user_data["awaiting"] = "caption"
        await render(query, tr("change_caption_prompt", lang))

    elif data == "action_voice":
        await render(query, tr("converting_voice", lang))
        ogg_path = await run_ffmpeg_to_voice(context)
        with open(ogg_path, "rb") as voice_file:
            await context.bot.send_voice(chat_id=update.effective_chat.id, voice=voice_file)
        ogg_path.unlink(missing_ok=True)
        await render(query, tr("voice_sent", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "action_apply_default":
        settings = load_user_settings(user_id)
        await apply_default_tags(context, settings)
        await render(query, tr("default_applied", lang), reply_markup=main_menu_keyboard(lang))

    elif data == "menu_caption_template":
        context.user_data["selected_genres"] = set()
        await render(query, tr("choose_genres", lang), reply_markup=genre_keyboard(lang, set()))

    elif data.startswith("genre_toggle_"):
        genre_key = data.replace("genre_toggle_", "")
        selected = context.user_data.setdefault("selected_genres", set())
        if genre_key in selected:
            selected.discard(genre_key)
        else:
            selected.add(genre_key)
        await render(query, tr("choose_genres", lang), reply_markup=genre_keyboard(lang, selected))

    elif data == "genre_done":
        selected = context.user_data.get("selected_genres", set())
        if not selected:
            await query.answer(tr("no_genre_selected", lang), show_alert=True)
            return
        # اولین ژانر انتخاب‌شده به‌عنوان ژانر اصلی برای شعار در نظر گرفته می‌شه
        context.user_data["primary_genre"] = sorted(selected)[0]
        primary_genre = context.user_data["primary_genre"]
        await render(query, tr("choose_slogan", lang), reply_markup=slogan_keyboard(lang, primary_genre))

    elif data.startswith("slogan_"):
        idx = int(data.replace("slogan_", ""))
        primary_genre = context.user_data.get("primary_genre", "pop")
        slogans = SLOGANS.get(primary_genre, SLOGANS["pop"])
        chosen = slogans[idx] if idx < len(slogans) else slogans[0]
        context.user_data["selected_slogan"] = chosen
        current_year = datetime.now().year
        await render(query, 
            tr("ask_year", lang, current_year=current_year),
            reply_markup=year_keyboard(lang),
        )
        context.user_data["awaiting"] = "caption_year"

    elif data.startswith("year_"):
        year = data.replace("year_", "")
        caption_text = build_caption_template(context, lang, year)
        context.user_data["caption"] = caption_text
        context.user_data["awaiting"] = None
        await render(query, 
            tr("caption_template_ready", lang) + "\n\n" + caption_text,
            reply_markup=main_menu_keyboard(lang),
        )

    elif data == "action_demo":
        options = ["30 sec", "45 sec", "60 sec", "90 sec", tr("demo_manual_option", lang)]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=tr("choose_demo_duration", lang),
            reply_markup=bottom_panel(options, columns=3),
        )
        context.user_data["awaiting"] = "reply_demo_duration"

    elif data in ("action_finish", "tags_save"):
        await send_final_file(update, context, lang)
        await render(query, tr("final_sent", lang))

    elif data == "show_lyrics":
        lyrics = get_tag_value(context, "lyrics")
        if lyrics:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=lyrics)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=tr("no_lyrics", lang))


# ---------- دریافت متن (برای مقادیر تگ / برش / کپشن) ----------

async def _finalize_demo(update, context, seconds: int, lang: str):
    status_msg = await update.message.reply_text(tr("making_demo", lang), reply_markup=ReplyKeyboardRemove())
    demo_path = await make_demo(context, seconds)
    work_path_for_tags = Path(context.user_data["work_path"])
    title, artist = get_title_artist(work_path_for_tags)
    display_name = title or context.user_data.get("display_filename") or "Melolux Track"
    safe_name = re.sub(r'[^\w\-. ]', '', display_name).strip() or "Melolux Track"
    with open(demo_path, "rb") as demo_file:
        await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=demo_file,
            filename=f"{safe_name} (Demo {seconds}s).mp3",
            title=title,
            performer=artist,
            caption=tr("demo_caption", lang, sec=seconds),
        )
    demo_path.unlink(missing_ok=True)
    context.user_data["awaiting"] = None
    await update_menu_message(context, tr("main_menu_title", lang), main_menu_keyboard(lang))
    try:
        await status_msg.delete()
    except Exception:
        pass


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        return

    text = update.message.text.strip()

    if awaiting == "reply_bitrate":
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            await update.message.reply_text(tr("demo_bad_number", lang))
            return
        bitrate = digits
        status_msg = await update.message.reply_text(tr("applying_bitrate", lang), reply_markup=ReplyKeyboardRemove())
        await run_ffmpeg_bitrate(context, bitrate)
        context.user_data["awaiting"] = None
        await update_menu_message(context, tr("bitrate_done", lang, bitrate=bitrate), main_menu_keyboard(lang))
        try:
            await status_msg.delete()
        except Exception:
            pass
        return

    if awaiting == "reply_effect":
        fx_map = {
            tr("fx_bass_boost", lang): "bass_boost",
            tr("fx_nightcore", lang): "nightcore",
            tr("fx_echo", lang): "echo",
            tr("fx_robotic", lang): "robotic",
            tr("fx_slowed", lang): "slowed",
        }
        effect_key = fx_map.get(text)
        if not effect_key:
            await update.message.reply_text(tr("choose_effect", lang))
            return
        status_msg = await update.message.reply_text(tr("applying_effect", lang), reply_markup=ReplyKeyboardRemove())
        await run_ffmpeg_effect(context, effect_key)
        context.user_data["awaiting"] = None
        await update_menu_message(context, tr("effect_done", lang), main_menu_keyboard(lang))
        try:
            await status_msg.delete()
        except Exception:
            pass
        return

    if awaiting == "reply_volume":
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            await update.message.reply_text(tr("demo_bad_number", lang))
            return
        percent = int(digits)
        status_msg = await update.message.reply_text(tr("applying_volume", lang), reply_markup=ReplyKeyboardRemove())
        await run_ffmpeg_volume(context, percent)
        context.user_data["awaiting"] = None
        await update_menu_message(context, tr("volume_done", lang, percent=percent), main_menu_keyboard(lang))
        try:
            await status_msg.delete()
        except Exception:
            pass
        return

    if awaiting == "reply_demo_duration":
        if text == tr("demo_manual_option", lang):
            context.user_data["awaiting"] = "reply_demo_manual"
            await update.message.reply_text(tr("demo_manual_prompt", lang), reply_markup=ReplyKeyboardRemove())
            return
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            await update.message.reply_text(tr("demo_bad_number", lang))
            return
        seconds = int(digits)
        await _finalize_demo(update, context, seconds, lang)
        return

    if awaiting == "reply_demo_manual":
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            await update.message.reply_text(tr("demo_bad_number", lang))
            return
        seconds = int(digits)
        await _finalize_demo(update, context, seconds, lang)
        return

    if awaiting == "cut":
        try:
            start_s, end_s = map(int, text.replace(" ", "").split("-"))
        except Exception:
            await update.message.reply_text(tr("cut_bad_format", lang))
            return
        status_msg = await update.message.reply_text(tr("cutting", lang))
        await run_ffmpeg_cut(context, start_s, end_s)
        context.user_data["awaiting"] = None
        await update_menu_message(context, tr("cut_done", lang), main_menu_keyboard(lang))
        try:
            await status_msg.delete()
        except Exception:
            pass
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    if awaiting.startswith("tag_"):
        field = awaiting.replace("tag_", "")
        set_single_tag(context, field, text)
        context.user_data["awaiting"] = None
        edited = context.user_data.setdefault("edited_tags", set())
        edited.add(field)
        await update_menu_message(context, with_metadata(context, tr("value_saved", lang), lang), tags_menu_keyboard(lang, edited))
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    if awaiting == "caption":
        context.user_data["caption"] = text
        context.user_data["awaiting"] = None
        await update_menu_message(context, tr("caption_saved", lang), main_menu_keyboard(lang))
        try:
            await update.message.delete()
        except Exception:
            pass
        return


async def handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    if context.user_data.get("awaiting") != "tag_picture":
        return

    message = update.effective_message
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id

    if not file_id:
        return

    file = await context.bot.get_file(file_id)
    img_path = TEMP_DIR / f"newcover_{user_id}.jpg"
    await file.download_to_drive(custom_path=str(img_path))
    set_cover_tag(context, img_path)
    context.user_data["cover_image_path"] = str(img_path)
    context.user_data["awaiting"] = None
    edited = context.user_data.setdefault("edited_tags", set())
    edited.add("picture")
    await refresh_audio_media(context, with_metadata(context, tr("new_cover_applied", lang), lang), tags_menu_keyboard(lang, edited))


# ---------- توابع تگ‌گذاری (mutagen) ----------

def extract_existing_cover(path: Path, user_id: int):
    """اگه فایل از قبل کاور (APIC) داشته باشه، به یه فایل jpg جدا استخراجش می‌کنه."""
    try:
        tags = ID3(path)
        for key in tags.keys():
            if key.startswith("APIC"):
                apic = tags[key]
                out_path = TEMP_DIR / f"existingcover_{user_id}.jpg"
                out_path.write_bytes(apic.data)
                return out_path
    except Exception:
        pass
    return None


def get_title_artist(path: Path):
    """عنوان و خواننده رو از تگ‌های فایل می‌خونه تا موقع ارسال به تلگرام صریح پاس داده بشه."""
    try:
        tags = ID3(path)
        title = str(tags["TIT2"].text[0]) if "TIT2" in tags else None
        artist = str(tags["TPE1"].text[0]) if "TPE1" in tags else None
        return title, artist
    except Exception:
        return None, None


def _load_tags(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def with_metadata(context, status_text: str, lang: str) -> str:
    """متن وضعیت رو با اطلاعات کامل موزیک ترکیب می‌کنه (مخصوص صفحه‌ی ادیت تگ‌ها)."""
    work_path = context.user_data.get("work_path")
    if work_path and Path(work_path).exists():
        return f"{status_text}\n\n{build_metadata_caption(context, Path(work_path), lang)}"
    return status_text


def build_metadata_caption(context, path: Path, lang: str) -> str:
    """کپشن کامل اطلاعات موزیک (تگ‌ها + مشخصات فنی) رو می‌سازه، دقیقاً مثل باتی که کاربر می‌خواد."""
    try:
        tags = ID3(path)
    except Exception:
        tags = {}

    def g(frame_id):
        try:
            return str(tags[frame_id].text[0]) if frame_id in tags else ""
        except Exception:
            return ""

    filename = context.user_data.get("custom_filename") or path.name
    title = g("TIT2")
    artist = g("TPE1")
    album = g("TALB")
    year = g("TDRC")
    track = g("TRCK")
    genre = g("TCON")
    try:
        lyrics = str(tags["USLT"].text) if "USLT" in tags else ""
    except Exception:
        lyrics = ""
    try:
        comment = str(tags["COMM"].text[0]) if "COMM" in tags else ""
    except Exception:
        comment = ""
    album_artist = g("TPE2")
    composer = g("TCOM")
    publisher = g("TPUB")
    disc = g("TPOS")

    def v(value, max_len=60):
        """اگه مقدار خالی بود ❌ نشون بده، وگرنه خود مقدار (با محدودیت طول برای متن‌های بلند)."""
        if not value:
            return "❌"
        return value[:max_len] + "…" if len(value) > max_len else value

    # اطلاعات فنی فایل
    bitrate = sample_rate = channel_mode = duration = "?"
    size_kib = "?"
    try:
        audio = MP3(path)
        bitrate = int(audio.info.bitrate / 1000)
        sample_rate = audio.info.sample_rate
        channel_modes = {0: "Stereo", 1: "Joint Stereo", 2: "Dual Channel", 3: "Mono"}
        channel_mode = channel_modes.get(getattr(audio.info, "mode", None), "Stereo")
        duration = int(audio.info.length)
        size_kib = int(path.stat().st_size / 1024)
    except Exception:
        pass

    lines = [
        f"🏷️ File Name : {v(filename)}",
        f"🎶 Title : {v(title)}",
        f"👤 Artists : {v(artist)}",
        f"🗂 Album : {v(album)}",
        f"📆 Year : {v(year)}",
        f"💿 Track N : {v(track)}",
        f"🎙 Genre : {v(genre)}",
        f"✍️ Lyrics : {v(lyrics)}",
        f"📝 Comment : {v(comment)}",
        f"👥 Album Artist : {v(album_artist)}",
        f"👨‍💻 Composer : {v(composer)}",
        f"👤 Publisher : {v(publisher)}",
        f"📀 Disc N : {v(disc)}",
        "--------------------",
        f"Bitrate : {bitrate} kbps",
        f"Sample Rate : {sample_rate} Hz",
        f"Channel Mode : {channel_mode}",
        f"Size : {size_kib} KiB",
        f"Duration : {duration} s",
    ]
    return "\n".join(lines)


def get_tag_value(context, field: str):
    """مقدار فعلی یه تگ خاص رو برمی‌گردونه (برای نمایش توی پنل جزئیات)."""
    if field == "filename":
        return context.user_data.get("custom_filename")
    path = Path(context.user_data["work_path"])
    try:
        tags = ID3(path)
    except Exception:
        return None
    try:
        if field == "comment":
            return str(tags["COMM"].text[0]) if "COMM" in tags else None
        if field == "lyrics":
            return str(tags["USLT"].text) if "USLT" in tags else None
        frame_cls = TAG_FIELDS[field]["frame"]
        frame_id = frame_cls.__name__
        return str(tags[frame_id].text[0]) if frame_id in tags else None
    except Exception:
        return None


def set_single_tag(context, field: str, value: str):
    if field == "filename":
        context.user_data["custom_filename"] = value
        return
    path = Path(context.user_data["work_path"])
    tags = _load_tags(path)
    if field == "comment":
        tags["COMM"] = COMM(encoding=3, lang="eng", desc="", text=value)
    elif field == "lyrics":
        tags["USLT"] = USLT(encoding=3, lang="eng", desc="", text=value)
    else:
        frame_cls = TAG_FIELDS[field]["frame"]
        frame_id = frame_cls.__name__
        tags[frame_id] = frame_cls(encoding=3, text=value)
    tags.save(path)


def delete_single_tag(context, field: str):
    """یه تگ خاص رو حذف می‌کنه (برای دکمه‌ی حذف توی پنل جزئیات)."""
    if field == "filename":
        context.user_data.pop("custom_filename", None)
        return
    path = Path(context.user_data["work_path"])
    tags = _load_tags(path)
    try:
        if field == "comment":
            tags.delall("COMM")
        elif field == "lyrics":
            tags.delall("USLT")
        else:
            frame_cls = TAG_FIELDS[field]["frame"]
            frame_id = frame_cls.__name__
            if frame_id in tags:
                del tags[frame_id]
        tags.save(path)
    except Exception:
        pass


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

async def _run(cmd: list):
    """اجرای دستور ffmpeg در یه ترد جدا تا event loop اصلی بات (برای همه‌ی کاربرها) قفل نشه."""
    await asyncio.to_thread(
        subprocess.run, cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


async def run_ffmpeg_cut(context, start_s: int, end_s: int):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"cut_{path.name}"
    await _run(["ffmpeg", "-y", "-i", str(path), "-ss", str(start_s), "-to", str(end_s), "-c", "copy", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_bitrate(context, bitrate: str):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"br_{path.name}"
    await _run(["ffmpeg", "-y", "-i", str(path), "-b:a", f"{bitrate}k", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_volume(context, percent: int):
    path = Path(context.user_data["work_path"])
    factor = percent / 100
    out_path = TEMP_DIR / f"vol_{path.name}"
    await _run(["ffmpeg", "-y", "-i", str(path), "-filter:a", f"volume={factor}", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_8d(context):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"8d_{path.name}"
    await _run(["ffmpeg", "-y", "-i", str(path), "-af", "apulsator=hz=0.09", str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_mixed_voice(context):
    """افکت میکس صدا (دوبل/کروس) با فیلتر chorus."""
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"mix_{path.name}"
    await _run([
        "ffmpeg", "-y", "-i", str(path),
        "-af", "chorus=0.6:0.9:55:0.4:0.25:2",
        str(out_path),
    ])
    out_path.replace(path)


EFFECT_FILTERS = {
    "bass_boost": "bass=g=12",
    "nightcore": "asetrate=44100*1.25,aresample=44100",
    "echo": "aecho=0.8:0.9:1000:0.3",
    "robotic": "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)'",
    "slowed": "asetrate=44100*0.85,aresample=44100",
}


async def run_ffmpeg_effect(context, effect_key: str):
    path = Path(context.user_data["work_path"])
    out_path = TEMP_DIR / f"fx_{path.name}"
    filt = EFFECT_FILTERS.get(effect_key, "anull")
    await _run(["ffmpeg", "-y", "-i", str(path), "-af", filt, str(out_path)])
    out_path.replace(path)


async def run_ffmpeg_to_voice(context) -> Path:
    path = Path(context.user_data["work_path"])
    ogg_path = TEMP_DIR / f"voice_{path.stem}.ogg"
    await _run(["ffmpeg", "-y", "-i", str(path), "-c:a", "libopus", "-b:a", "64k", str(ogg_path)])
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
        f"*{slogan_text}* {emoji}\n"
        f"{download_line} 📥\n\n"
        f"@MeloLux 🆔🎧\n\n"
        f"{hashtags} #{year}"
    )
    return caption


async def make_demo(context, demo_len: int = 45) -> Path:
    path = Path(context.user_data["work_path"])
    result = await asyncio.to_thread(
        subprocess.run,
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())
    demo_len = min(demo_len, int(duration)) if duration else demo_len
    start = max(0, (duration - demo_len) / 2)
    demo_path = TEMP_DIR / f"demo_{path.name}"
    await _run(["ffmpeg", "-y", "-i", str(path), "-ss", str(start), "-t", str(demo_len), "-c", "copy", str(demo_path)])
    return demo_path


# ---------- اجرای بات ----------

def main():
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("setartist", set_artist))
    app.add_handler(CommandHandler("setcover", set_cover))
    app.add_handler(CommandHandler("myinfo", my_info))

    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo_input))

    logger.info("Bot is running... / بات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
