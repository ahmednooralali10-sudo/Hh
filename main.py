import os
import re
import time
import uuid
import random
import asyncio
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import FastAPI
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# محاولة استيراد مكتبات البث الصوتي والمكالمات الجماعية
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream
    VOICE_CALLS_AVAILABLE = True
except ImportError:
    PyTgCalls = None
    MediaStream = None
    VOICE_CALLS_AVAILABLE = False

# ==========================================
# قراءة متغيرات البيئة من Render
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
TARGET_CHAT = os.environ.get("TARGET_CHAT", "")
MY_TELEGRAM_ID = int(os.environ.get("MY_TELEGRAM_ID", 0))
STICKER_ID = os.environ.get("STICKER_ID", "")

DEFAULT_UID = "11877711994"
DEFAULT_AFK_MSG = "أهلاً يا حلو 🤍\nأنا الحين ماني متصل، اترك رسالتك وإن شاء الله برد عليك ياقلبي 🫀"
KSA_TZ = timezone(timedelta(hours=3))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_AUDIO_FILE = os.path.join(BASE_DIR, "mahdi.m4a")

if TARGET_CHAT and TARGET_CHAT.lstrip("-").isdigit():
    TARGET_CHAT = int(TARGET_CHAT)

app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "Mahdi Userbot (Local mahdi.m4a + Voice + AI) is running!",
        "voice_calls_ready": VOICE_CALLS_AVAILABLE,
        "local_audio_exists": os.path.exists(LOCAL_AUDIO_FILE),
    }


user_client = TelegramClient(
    StringSession(SESSION_STRING) if SESSION_STRING else "user_session",
    API_ID,
    API_HASH,
)

call_py = PyTgCalls(user_client) if VOICE_CALLS_AVAILABLE else None

# ==========================================
# حالة التشغيل والذاكرة المؤقتة
# ==========================================
START_TIME = time.time()
AFK_ENABLED = True
DAILY_SCHED_ENABLED = True
SHORTCUTS_ENABLED = True
AI_ENABLED = True

AFK_TEXT = DEFAULT_AFK_MSG
AFK_REPLIES_COUNT = 0
LIKE_RUNS_COUNT = 0
COMMANDS_USED_COUNT = 0
SHORTCUT_TRIGGERS_COUNT = 0
AI_REQUESTS_COUNT = 0
VOICE_PLAYS_COUNT = 0

LAST_RESULT = "لم يتم تسجيل أي نتيجة لايك حتى الآن."
RESULT_HISTORY: list[str] = []
SHORTCUTS: dict[str, list[str]] = {}
NOTES: list[str] = []
ACTIVE_CALLS: dict[int, dict] = {}
VOICE_QUEUES: dict[int, list[dict]] = {}


def record_history(entry: str) -> None:
    global LAST_RESULT
    LAST_RESULT = entry
    RESULT_HISTORY.append(entry)
    if len(RESULT_HISTORY) > 10:
        del RESULT_HISTORY[0]


def format_uptime() -> str:
    elapsed = int(time.time() - START_TIME)
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}ي")
    if hours:
        parts.append(f"{hours}س")
    if minutes:
        parts.append(f"{minutes}د")
    parts.append(f"{seconds}ث")
    return " ".join(parts)


def safe_calc(expr: str) -> str:
    cleaned = expr.strip()
    if not re.fullmatch(r"[0-9+\-*/().%\s]+", cleaned):
        return "❌ يُسمح بالأرقام والعمليات الحسابية الأساسية (+ - * / % ( )) فقط."
    try:
        result = eval(cleaned, {"__builtins__": {}}, {})
        return f"🧮 **النتيجة:** `{result}`"
    except ZeroDivisionError:
        return "❌ خطأ: القسمة على صفر غير مسموحة."
    except Exception:
        return "❌ تعبير رياضي غير صالح."


def format_shortcuts_list() -> str:
    if not SHORTCUTS:
        return "📭 لا توجد اختصارات محفوظة حالياً. استخدم `/sa ا هلا` لإضافة اختصار."
    lines = ["⚡ **قائمة الاختصارات المحفوظة:**\n"]
    for key, phrases in SHORTCUTS.items():
        items = " | ".join(f"`{p}`" for p in phrases)
        lines.append(f"• **`{key}`** ({len(phrases)}): {items}")
    return "\n".join(lines)


def resolve_local_or_url_track(query: str) -> dict:
    q = (query or "").strip()
    if not q or q.lower() in {"mahdi", "mahdi.m4a", "local", "file"}:
        if not os.path.exists(LOCAL_AUDIO_FILE):
            raise FileNotFoundError(
                "لم يتم العثور على الملف mahdi.m4a داخل مجلد المشروع. ارفع mahdi.m4a بجانب main.py في GitHub."
            )
        return {
            "stream_url": LOCAL_AUDIO_FILE,
            "title": "mahdi.m4a (ملف صوتي محلي)",
            "duration": 0,
            "webpage_url": "ملف محلي داخل المجلد",
        }

    candidate_path = os.path.join(BASE_DIR, q)
    if os.path.isfile(candidate_path):
        return {
            "stream_url": candidate_path,
            "title": f"{os.path.basename(candidate_path)} (ملف صوتي محلي)",
            "duration": 0,
            "webpage_url": "ملف محلي داخل المجلد",
        }

    if re.match(r"^https?://", q, re.IGNORECASE) and re.search(
        r"\.(mp3|m4a|ogg|wav|flac|aac|opus)(\?.*)?$", q, re.IGNORECASE
    ):
        return {
            "stream_url": q,
            "title": "ملف صوتي مباشر من الرابط",
            "duration": 0,
            "webpage_url": q,
        }

    raise RuntimeError(
        "أرسل `/vioc` أو `/vioc mahdi.m4a` لتشغيل ملفك المحلي داخل المجلد، أو أرسل رابط ملف صوتي مباشر (.mp3 / .m4a / .ogg)."
    )


async def start_voice_stream(chat_id: int, track: dict) -> None:
    global VOICE_PLAYS_COUNT
    if not (VOICE_CALLS_AVAILABLE and call_py):
        raise RuntimeError(
            "مكتبات البث الصوتي غير مكتملة على السيرفر. تأكد من تثبيت py-tgcalls و ffmpeg."
        )
    await call_py.play(
        chat_id,
        MediaStream(track["stream_url"]),
    )
    ACTIVE_CALLS[chat_id] = {
        "title": track["title"],
        "duration": track["duration"],
        "url": track["webpage_url"],
        "paused": False,
        "started_at": time.time(),
    }
    VOICE_PLAYS_COUNT += 1


async def ask_free_ai(prompt: str) -> str:
    url = f"https://text.pollinations.ai/{quote(prompt)}"
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text:
                return "❌ لم يرجع الذكاء الاصطناعي رداً واضحاً، جرّب صياغة أخرى."
            if len(text) > 3500:
                text = text[:3500] + "\n\n... (تم اختصار الرد لطوله)"
            return text
    except Exception as e:
        return f"❌ تعذر الاتصال بالذكاء الاصطناعي حالياً: {e}"


async def execute_like_and_fetch_result(uid: str = DEFAULT_UID) -> str:
    global LIKE_RUNS_COUNT
    LIKE_RUNS_COUNT += 1
    try:
        sent_msg = await user_client.send_message(TARGET_CHAT, f"/like me {uid}")

        for _ in range(20):
            await asyncio.sleep(1)
            messages = await user_client.get_messages(TARGET_CHAT, limit=6, min_id=sent_msg.id)
            for msg in messages:
                if msg.text and ("UID" in msg.text or "NickName" in msg.text or "Added" in msg.text):
                    formatted = f"📊 **نتيجة اللايك (UID: `{uid}`):**\n\n{msg.text}"
                    record_history(formatted)
                    return formatted

        fallback = f"✅ تم إرسال أمر اللايك لـ `{uid}` للقروب، ولكن لم يرد بوت اللايكات خلال 20 ثانية."
        record_history(fallback)
        return fallback
    except Exception as e:
        return f"❌ خطأ أثناء تنفيذ أمر اللايك: {e}"


# ==========================================
# أوامر المكالمات الصوتية وبث الملفات (/vioc و /voic)
# ==========================================
@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/(?:vioc|voic)(?:\s+(.+))?$"))
async def vioc_play_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1

    if event.is_private:
        await event.edit("⚠️ هذا الأمر يعمل داخل **القروبات** التي تحتوي على محادثة صوتية نشطة.")
        return

    query = (event.pattern_match.group(1) or "").strip()

    if not (VOICE_CALLS_AVAILABLE and call_py):
        await event.edit(
            "❌ **تجهيز السيرفر مطلوب لتشغيل المكالمات الصوتية:**\n"
            "تأكد من تثبيت `py-tgcalls` و `ffmpeg` على السيرفر."
        )
        return

    status = await event.edit("🔊 جاري تجهيز ملف `mahdi.m4a` والانضمام لمكالمة القروب...")
    try:
        track = resolve_local_or_url_track(query)
        await start_voice_stream(event.chat_id, track)
        await status.edit(
            f"🔊 **تم الدخول للمكالمة وبدأ تشغيل الصوت!**\n\n"
            f"🎵 **الملف / المقطع:** {track['title']}\n"
            f"📍 **المصدر:** {track['webpage_url']}"
        )
    except Exception as e:
        await status.edit(
            f"❌ **تعذر تشغيل الصوت في المكالمة:**\n`{e}`\n\n"
            "💡 تأكد من وجود `mahdi.m4a` داخل مجلد المشروع وأن المحادثة الصوتية مفتوحة في القروب."
        )


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/vqueue\s+(.+)$"))
async def vqueue_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    if event.is_private:
        await event.edit("⚠️ يعمل هذا الأمر داخل القروبات فقط.")
        return
    if not VOICE_CALLS_AVAILABLE:
        await event.edit("❌ مكتبات الصوت غير مثبتة على السيرفر.")
        return
    query = event.pattern_match.group(1).strip()
    msg = await event.edit("⏳ جاري إضافة المقطع لقائمة الانتظار...")
    try:
        track = resolve_local_or_url_track(query)
        VOICE_QUEUES.setdefault(event.chat_id, []).append(track)
        pos = len(VOICE_QUEUES[event.chat_id])
        await msg.edit(f"➕ **تمت الإضافة لقائمة الانتظار (الترتيب #{pos}):**\n🎵 {track['title']}")
    except Exception as e:
        await msg.edit(f"❌ خطأ أثناء الإضافة: `{e}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/vskip$"))
async def vskip_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    queue = VOICE_QUEUES.get(event.chat_id, [])
    if not queue:
        await event.edit("📭 قائمة الانتظار فارغة. استخدم `/vstop` لإنهاء المكالمة.")
        return
    next_track = queue.pop(0)
    msg = await event.edit("⏭️ جاري التخطي للمقطع التالي...")
    try:
        await start_voice_stream(event.chat_id, next_track)
        await msg.edit(f"🔊 **يُعرض الآن:** {next_track['title']}")
    except Exception as e:
        await msg.edit(f"❌ تعذر التخطي: `{e}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/vpause$"))
async def vpause_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    if not call_py:
        await event.edit("❌ خدمة المكالمات غير مفعلة.")
        return
    try:
        await call_py.pause(event.chat_id)
        if event.chat_id in ACTIVE_CALLS:
            ACTIVE_CALLS[event.chat_id]["paused"] = True
        await event.edit("⏸️ تم إيقاف الصوت مؤقتاً في المكالمة.")
    except Exception as e:
        await event.edit(f"❌ تعذر الإيقاف المؤقت: `{e}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/vresume$"))
async def vresume_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    if not call_py:
        await event.edit("❌ خدمة المكالمات غير مفعلة.")
        return
    try:
        await call_py.resume(event.chat_id)
        if event.chat_id in ACTIVE_CALLS:
            ACTIVE_CALLS[event.chat_id]["paused"] = False
        await event.edit("▶️ تم استئناف الصوت في المكالمة.")
    except Exception as e:
        await event.edit(f"❌ تعذر الاستئناف: `{e}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/vstop$"))
async def vstop_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    if not call_py:
        await event.edit("❌ خدمة المكالمات غير مفعلة.")
        return
    try:
        await call_py.leave_call(event.chat_id)
        ACTIVE_CALLS.pop(event.chat_id, None)
        VOICE_QUEUES.pop(event.chat_id, None)
        await event.edit("⏹️ تم إيقاف البث ومغادرة مكالمة القروب.")
    except Exception as e:
        await event.edit(f"❌ تعذر مغادرة المكالمة: `{e}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/vnow$"))
async def vnow_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    current = ACTIVE_CALLS.get(event.chat_id)
    if not current:
        await event.edit("🔇 لا يوجد بث صوتي نشط حالياً في هذا القروب.")
        return
    state = "متوقف مؤقتاً ⏸️" if current.get("paused") else "يعمل الآن 🔊"
    q_len = len(VOICE_QUEUES.get(event.chat_id, []))
    await event.edit(
        f"🎧 **حالة البث الصوتي في القروب:**\n"
        f"• **الملف / المقطع:** {current['title']}\n"
        f"• **الحالة:** {state}\n"
        f"• **في الانتظار:** `{q_len}` مقاطع"
    )


@user_client.on(events.NewMessage(pattern=r"(?s)^/ai(?:\s+(.+))?$"))
async def ai_cmd(event):
    global AI_REQUESTS_COUNT, AI_ENABLED
    prompt = (event.pattern_match.group(1) or "").strip()

    if event.out and prompt.lower() == "on":
        AI_ENABLED = True
        await event.edit("✅ تم **تشغيل** أمر `/ai` للجميع.")
        return

    if event.out and prompt.lower() == "off":
        AI_ENABLED = False
        await event.edit("⏸️ تم **إيقاف** أمر `/ai` مؤقتاً.")
        return

    if not AI_ENABLED and not event.out:
        return

    if not prompt:
        msg = "🤖 اكتب سؤالك بعد الأمر مثل:\n`/ai وش أفضل طريقة للمذاكرة؟`"
        if event.out:
            await event.edit(msg)
        else:
            await event.reply(msg)
        return

    AI_REQUESTS_COUNT += 1
    if event.out:
        status_msg = await event.edit("🤖 جاري التفكير والرد...")
        answer = await ask_free_ai(prompt)
        await status_msg.edit(f"🤖 **الرد:**\n\n{answer}")
    else:
        thinking = await event.reply("🤖 جاري التفكير...")
        answer = await ask_free_ai(prompt)
        await thinking.edit(f"🤖 **الرد:**\n\n{answer}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/mahdi$"))
async def mahdi_menu(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    afk_state = "مفعل ✅" if AFK_ENABLED else "متوقف ⏸️"
    sched_state = "مفعل ✅" if DAILY_SCHED_ENABLED else "متوقف ⏸️"
    sa_state = "مفعل ✅" if SHORTCUTS_ENABLED else "متوقف ⏸️"
    ai_state = "مفعل ✅" if AI_ENABLED else "متوقف ⏸️"
    voice_state = "جاهز ✅" if VOICE_CALLS_AVAILABLE else "يحتاج ffmpeg/pytgcalls ⚠️"
    file_state = "موجود ✅" if os.path.exists(LOCAL_AUDIO_FILE) else "غير مرفوع ⚠️"
    menu_text = (
        "👑 **قائمة أوامر يوزر بوت مهدي (53 ميزة):**\n\n"
        "**🎵 المكالمات الصوتية (ملف mahdi.m4a):**\n"
        "• `/vioc` أو `/voic` — دخول مكالمة القروب وتشغيل `mahdi.m4a` مباشرة\n"
        "• `/vioc mahdi.m4a` أو `/vioc <رابط صوت مباشر>`\n"
        "• `/vqueue <ملف/رابط>` | `/vskip` | `/vpause` | `/vresume` | `/vstop` | `/vnow`\n\n"
        "**🤖 الذكاء الاصطناعي (متاح للجميع):**\n"
        "• `/ai <النص>` — سؤال الذكاء الاصطناعي المجاني\n"
        "• `/ai on` و `/ai off` — تشغيل أو إيقاف `/ai` (لك فقط)\n\n"
        "**⚡ الاختصارات الذكية:**\n"
        "• `/sa <اختصار> <نص>` — إضافة عبارة لاختصار (يدعم تعدد العبارات)\n"
        "• `/sa` أو `/salist` — عرض كل الاختصارات\n"
        "• `/sadel <اختصار>` — حذف اختصار | `/saclear` — مسح الكل\n"
        "• `/saon` و `/saoff` — تشغيل أو إيقاف الاختصارات\n\n"
        "**🎯 اللايكات والجدولة:**\n"
        f"• `/like` — إرسال للآيدي الافتراضي (`{DEFAULT_UID}`)\n"
        "• `/like <UID>` — إرسال لآيدي محدد | `/like2 <UID1> <UID2>`\n"
        "• `/repeat <1-5> [UID]` — تكرار آمن مع تهدئة\n"
        "• `/last` | `/history` | `/clearhist` | `/sched [on|off]`\n\n"
        "**💬 الرد التلقائي (AFK):**\n"
        "• `/afk` | `/afkon` | `/afkoff` | `/afkmsg <نص>` | `/afkreset` | `/afkcount`\n\n"
        "**✉️ الرسائل والملاحظات والأدوات:**\n"
        "• `/say` | `/echo` | `/del` | `/edit` | `/pin` | `/unpin` | `/copy`\n"
        "• `/note` | `/notes` | `/delnote` | `/clearnotes`\n"
        "• `/id` | `/info` | `/ping` | `/status` | `/stats` | `/time` | `/uuid`\n"
        "• `/calc` | `/rev` | `/upper` | `/lower` | `/len` | `/flip` | `/roll`\n\n"
        f"⚙️ **الصوت:** {voice_state} | **mahdi.m4a:** {file_state} | **AI:** {ai_state} | **AFK:** {afk_state}"
    )
    await event.edit(menu_text)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/sa(?:\s+(\S+)(?:\s+(.+))?)?$"))
async def sa_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    shortcut = (event.pattern_match.group(1) or "").strip()
    phrase = (event.pattern_match.group(2) or "").strip()

    if not shortcut:
        await event.edit(format_shortcuts_list())
        return

    if not phrase:
        existing = SHORTCUTS.get(shortcut)
        if not existing:
            await event.edit(f"ℹ️ الاختصار `{shortcut}` غير مسجل. لإضافته: `/sa {shortcut} نصك`")
        else:
            joined = "\n".join(f"{i+1}. {p}" for i, p in enumerate(existing))
            await event.edit(f"⚡ **عبارات الاختصار `{shortcut}`:**\n{joined}")
        return

    SHORTCUTS.setdefault(shortcut, []).append(phrase)
    total_for_key = len(SHORTCUTS[shortcut])
    await event.edit(f"✅ تمت إضافة العبارة إلى الاختصار `{shortcut}` (الإجمالي لهذا الاختصار: `{total_for_key}`).")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/salist$"))
async def salist_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(format_shortcuts_list())


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/sadel\s+(\S+)$"))
async def sadel_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    key = event.pattern_match.group(1).strip()
    if key in SHORTCUTS:
        del SHORTCUTS[key]
        await event.edit(f"🗑️ تم حذف الاختصار `{key}` وجميع عباراته.")
    else:
        await event.edit(f"⚠️ الاختصار `{key}` غير موجود.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/saclear$"))
async def saclear_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    SHORTCUTS.clear()
    await event.edit("🧹 تم مسح جميع الاختصارات.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/saon$"))
async def saon_cmd(event):
    global SHORTCUTS_ENABLED, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    SHORTCUTS_ENABLED = True
    await event.edit("✅ تم **تشغيل** التوسيع التلقائي للاختصارات.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/saoff$"))
async def saoff_cmd(event):
    global SHORTCUTS_ENABLED, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    SHORTCUTS_ENABLED = False
    await event.edit("⏸️ تم **إيقاف** التوسيع التلقائي للاختصارات.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/like(?:\s+(\d+))?$"))
async def manual_like(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    custom_uid = event.pattern_match.group(1) or DEFAULT_UID
    wait_msg = await event.edit(f"⏳ جاري إرسال أمر اللايك لـ `{custom_uid}` وانتظار النتيجة...")
    result = await execute_like_and_fetch_result(custom_uid)
    await wait_msg.edit(result)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/like2\s+(\d+)\s+(\d+)$"))
async def like_two(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    uid1, uid2 = event.pattern_match.group(1), event.pattern_match.group(2)
    msg = await event.edit(f"⏳ جاري تنفيذ اللايك الأول لـ `{uid1}`...")
    res1 = await execute_like_and_fetch_result(uid1)
    await msg.edit(f"{res1}\n\n⏸️ تهدئة 5 ثوانٍ قبل الآيدي الثاني...")
    await asyncio.sleep(5)
    res2 = await execute_like_and_fetch_result(uid2)
    await msg.edit(f"{res1}\n\n──────────────\n\n{res2}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/repeat\s+([1-5])(?:\s+(\d+))?$"))
async def repeat_like(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    count = int(event.pattern_match.group(1))
    uid = event.pattern_match.group(2) or DEFAULT_UID
    msg = await event.edit(f"🔁 بدء تنفيذ `{count}` محاولات لـ `{uid}` بفاصل 8 ثوانٍ...")
    outputs = []
    for i in range(1, count + 1):
        res = await execute_like_and_fetch_result(uid)
        outputs.append(f"**[{i}/{count}]** {res}")
        if i < count:
            await msg.edit(f"⏳ اكتملت المحاولة {i}/{count}، انتظار 8 ثوانٍ...")
            await asyncio.sleep(8)
    await msg.edit("\n\n".join(outputs))


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/last$"))
async def last_result_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(LAST_RESULT)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/history$"))
async def history_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    if not RESULT_HISTORY:
        await event.edit("📭 لا يوجد سجل نتائج محفوظ حالياً.")
        return
    joined = "\n\n━━━━━━━━━━━━━━\n\n".join(RESULT_HISTORY[-5:])
    await event.edit(f"🗂️ **آخر النتائج المحفوظة (حتى 5 الأحدث):**\n\n{joined}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/clearhist$"))
async def clear_history_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    RESULT_HISTORY.clear()
    await event.edit("🧹 تم مسح سجل النتائج المؤقت بنجاح.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^/sched(?:\s+(on|off))?$"))
async def sched_cmd(event):
    global DAILY_SCHED_ENABLED, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    arg = (event.pattern_match.group(1) or "").lower()
    if arg == "on":
        DAILY_SCHED_ENABLED = True
        await event.edit("✅ تم **تفعيل** الجدولة اليومية الساعة 5:00 فجراً.")
    elif arg == "off":
        DAILY_SCHED_ENABLED = False
        await event.edit("⏸️ تم **إيقاف** الجدولة اليومية الساعة 5:00 فجراً.")
    else:
        state = "مفعلة ✅" if DAILY_SCHED_ENABLED else "متوقفة ⏸️"
        await event.edit(f"⏰ **حالة الجدولة اليومية (5:00 فجراً بتوقيت السعودية):** {state}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/afk$"))
async def toggle_afk(event):
    global AFK_ENABLED, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    AFK_ENABLED = not AFK_ENABLED
    state_msg = "✅ تم **تفعيل** الرد التلقائي على الرسائل الخاصة." if AFK_ENABLED else "⏸️ تم **إيقاف** الرد التلقائي على الرسائل الخاصة."
    await event.edit(state_msg)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/afkon$"))
async def afk_on(event):
    global AFK_ENABLED, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    AFK_ENABLED = True
    await event.edit("✅ تم **تشغيل** الرد التلقائي (AFK).")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/afkoff$"))
async def afk_off(event):
    global AFK_ENABLED, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    AFK_ENABLED = False
    await event.edit("⏸️ تم **إيقاف** الرد التلقائي (AFK).")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/afkmsg\s+(.+)$"))
async def set_afk_msg(event):
    global AFK_TEXT, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    AFK_TEXT = event.pattern_match.group(1).strip()
    await event.edit(f"✅ تم تحديث رسالة الرد التلقائي:\n\n{AFK_TEXT}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/afkreset$"))
async def reset_afk_msg(event):
    global AFK_TEXT, COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    AFK_TEXT = DEFAULT_AFK_MSG
    await event.edit("🔄 تم استعادة رسالة الرد التلقائي الافتراضية.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/afkcount$"))
async def afk_count_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(f"💬 عدد الردود التلقائية المرسلة منذ التشغيل: `{AFK_REPLIES_COUNT}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/say\s+(.+)$"))
async def say_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(event.pattern_match.group(1))


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/echo\s+(.+)$"))
async def echo_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(f"🗣️ {event.pattern_match.group(1)}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/del$"))
async def del_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    reply = await event.get_reply_message()
    if not reply:
        await event.edit("⚠️ رد على رسالة أولاً ثم اكتب `/del`.")
        return
    try:
        await reply.delete()
        await event.delete()
    except Exception as e:
        await event.edit(f"❌ تعذر حذف الرسالة: {e}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/edit\s+(.+)$"))
async def edit_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    reply = await event.get_reply_message()
    new_text = event.pattern_match.group(1)
    if not reply or not reply.out:
        await event.edit("⚠️ يجب الرد على **رسالة أرسلتها أنت** لتعديلها عبر `/edit`.")
        return
    try:
        await reply.edit(new_text)
        await event.delete()
    except Exception as e:
        await event.edit(f"❌ تعذر التعديل: {e}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/pin$"))
async def pin_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    reply = await event.get_reply_message()
    if not reply:
        await event.edit("⚠️ رد على رسالة لتثبيتها بـ `/pin`.")
        return
    try:
        await user_client.pin_message(event.chat_id, reply.id, notify=False)
        await event.edit("📌 تم تثبيت الرسالة.")
    except Exception as e:
        await event.edit(f"❌ تعذر التثبيت: {e}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/unpin$"))
async def unpin_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    reply = await event.get_reply_message()
    try:
        await user_client.unpin_message(event.chat_id, reply.id if reply else None)
        await event.edit("📍 تم إلغاء تثبيت الرسالة.")
    except Exception as e:
        await event.edit(f"❌ تعذر إلغاء التثبيت: {e}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/copy$"))
async def copy_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    reply = await event.get_reply_message()
    if not reply or not reply.raw_text:
        await event.edit("⚠️ رد على رسالة تحتوي على نص لنسخه عبر `/copy`.")
        return
    await event.edit(reply.raw_text)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/note\s+(.+)$"))
async def add_note_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    note = event.pattern_match.group(1).strip()
    NOTES.append(note)
    await event.edit(f"📝 تم حفظ الملاحظة رقم `{len(NOTES)}`.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/notes$"))
async def list_notes_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    if not NOTES:
        await event.edit("📭 لا توجد ملاحظات محفوظة حالياً.")
        return
    text = "📒 **الملاحظات المحفوظة:**\n\n" + "\n".join(f"`{i+1}.` {n}" for i, n in enumerate(NOTES))
    await event.edit(text)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/delnote\s+(\d+)$"))
async def del_note_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    idx = int(event.pattern_match.group(1)) - 1
    if 0 <= idx < len(NOTES):
        removed = NOTES.pop(idx)
        await event.edit(f"🗑️ تم حذف الملاحظة: `{removed}`")
    else:
        await event.edit("⚠️ رقم الملاحظة غير صحيح.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/clearnotes$"))
async def clear_notes_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    NOTES.clear()
    await event.edit("🧹 تم مسح جميع الملاحظات.")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/id$"))
async def id_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    reply = await event.get_reply_message()
    lines = [f"💬 **Chat ID:** `{event.chat_id}`"]
    if reply:
        lines.append(f"📩 **Replied Message ID:** `{reply.id}`")
        if reply.sender_id:
            lines.append(f"👤 **Replied Sender ID:** `{reply.sender_id}`")
    await event.edit("\n".join(lines))


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/info(?:\s+(.+))?$"))
async def info_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    target_arg = (event.pattern_match.group(1) or "").strip()
    reply = await event.get_reply_message()
    try:
        if target_arg:
            entity = await user_client.get_entity(int(target_arg) if target_arg.lstrip("-").isdigit() else target_arg)
        elif reply and reply.sender_id:
            entity = await user_client.get_entity(reply.sender_id)
        else:
            entity = await event.get_chat()

        title = getattr(entity, "title", None) or " ".join(
            x for x in [getattr(entity, "first_name", ""), getattr(entity, "last_name", "")] if x
        ) or "غير متوفر"
        username = f"@{entity.username}" if getattr(entity, "username", None) else "لا يوجد"
        await event.edit(
            f"🪪 **معلومات الكيان:**\n"
            f"• **الاسم:** {title}\n"
            f"• **المعرف (`ID`):** `{entity.id}`\n"
            f"• **اليوزر:** {username}"
        )
    except Exception as e:
        await event.edit(f"❌ تعذر جلب المعلومات: {e}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/ping$"))
async def ping_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    t0 = time.perf_counter()
    await event.edit("🏓 جاري قياس السرعة...")
    ms = int((time.perf_counter() - t0) * 1000)
    await event.edit(f"🏓 **Pong!** سرعة الاستجابة: `{ms} ms`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/status$"))
async def status_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    afk_state = "مفعل ✅" if AFK_ENABLED else "متوقف ⏸️"
    sched_state = "مفعل ✅" if DAILY_SCHED_ENABLED else "متوقف ⏸️"
    sa_state = "مفعل ✅" if SHORTCUTS_ENABLED else "متوقف ⏸️"
    ai_state = "مفعل ✅" if AI_ENABLED else "متوقف ⏸️"
    voice_state = "جاهز ✅" if VOICE_CALLS_AVAILABLE else "يحتاج ffmpeg/pytgcalls ⚠️"
    file_state = "موجود ✅" if os.path.exists(LOCAL_AUDIO_FILE) else "غير مرفوع ⚠️"
    text = (
        "✅ **اليوزر بوت يعمل بكفاءة تامة**\n"
        f"⏱️ **مدة التشغيل:** `{format_uptime()}`\n"
        f"🎵 **البث الصوتي:** {voice_state}\n"
        f"📁 **ملف mahdi.m4a:** {file_state}\n"
        f"🤖 **الذكاء الاصطناعي:** {ai_state}\n"
        f"💬 **الرد التلقائي:** {afk_state}\n"
        f"⚡ **الاختصارات:** {sa_state}\n"
        f"⏰ **جدولة 5:00 فجراً:** {sched_state}"
    )
    await event.edit(text)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/stats$"))
async def stats_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    text = (
        "📈 **إحصاءات الجلسة الحالية:**\n"
        f"• **مدة التشغيل:** `{format_uptime()}`\n"
        f"• **الأوامر المنفذة:** `{COMMANDS_USED_COUNT}`\n"
        f"• **مقاطع الصوت المشغّلة:** `{VOICE_PLAYS_COUNT}`\n"
        f"• **طلبات /ai:** `{AI_REQUESTS_COUNT}`\n"
        f"• **الاختصارات المنفذة:** `{SHORTCUT_TRIGGERS_COUNT}`\n"
        f"• **عمليات اللايك المنفذة:** `{LIKE_RUNS_COUNT}`\n"
        f"• **ردود AFK المرسلة:** `{AFK_REPLIES_COUNT}`\n"
        f"• **الاختصارات المسجلة:** `{len(SHORTCUTS)}` | **الملاحظات:** `{len(NOTES)}`"
    )
    await event.edit(text)


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/time$"))
async def time_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    now_ksa = datetime.now(KSA_TZ)
    await event.edit(f"🕒 **الوقت الحالي (السعودية +03:00):**\n`{now_ksa.strftime('%Y-%m-%d %H:%M:%S')}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/uuid$"))
async def uuid_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(f"🔑 `{uuid.uuid4().hex[:12]}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/flip$"))
async def flip_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(f"🪙 **النتيجة:** {random.choice(['وجه (صورة) 🙂', 'كتابة ✍️'])}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/roll(?:\s+(\d+))?$"))
async def roll_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    sides = int(event.pattern_match.group(1) or 6)
    sides = max(2, min(sides, 1000))
    await event.edit(f"🎲 **الرقم العشوائي (1-{sides}):** `{random.randint(1, sides)}`")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/calc\s+(.+)$"))
async def calc_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(safe_calc(event.pattern_match.group(1)))


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/rev\s+(.+)$"))
async def rev_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    txt = event.pattern_match.group(1)
    await event.edit(f"🔁 **النص معكوساً:**\n{txt[::-1]}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/upper\s+(.+)$"))
async def upper_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(event.pattern_match.group(1).upper())


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/lower\s+(.+)$"))
async def lower_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(event.pattern_match.group(1).lower())


@user_client.on(events.NewMessage(outgoing=True, pattern=r"(?s)^/len\s+(.+)$"))
async def len_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    txt = event.pattern_match.group(1)
    words = len(txt.split())
    chars = len(txt)
    await event.edit(f"📏 **طول النص:** `{chars}` حرف | `{words}` كلمة")


@user_client.on(events.NewMessage(outgoing=True))
async def expand_shortcut_handler(event):
    global SHORTCUT_TRIGGERS_COUNT
    if not SHORTCUTS_ENABLED:
        return
    raw = (event.raw_text or "").strip()
    if not raw or raw.startswith("/"):
        return
    phrases = SHORTCUTS.get(raw)
    if not phrases:
        return

    SHORTCUT_TRIGGERS_COUNT += 1
    chat_id = event.chat_id
    reply_to_id = event.reply_to_msg_id
    try:
        await event.delete()
        for idx, phrase in enumerate(phrases):
            await user_client.send_message(chat_id, phrase, reply_to=reply_to_id if idx == 0 else None)
            if idx < len(phrases) - 1:
                await asyncio.sleep(0.6)
    except Exception as e:
        print(f"خطأ في توسيع الاختصار '{raw}': {e}")


@user_client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def auto_reply(event):
    global AFK_REPLIES_COUNT
    if not AFK_ENABLED:
        return
    if event.sender_id == MY_TELEGRAM_ID or event.out:
        return
    raw = (event.raw_text or "").strip()
    if raw.startswith("/ai"):
        return
    try:
        if STICKER_ID:
            await event.respond(AFK_TEXT, file=STICKER_ID)
        else:
            await event.respond(AFK_TEXT)
        AFK_REPLIES_COUNT += 1
    except Exception as e:
        print(f"خطأ في الرد التلقائي: {e}")


async def daily_task():
    await asyncio.sleep(25)
    print("بدء نظام الجدولة اليومية لإرسال اللايك الساعة 5:00 فجراً...")
    while True:
        local_now = datetime.now(KSA_TZ)
        if DAILY_SCHED_ENABLED and local_now.hour == 5 and local_now.minute == 0:
            try:
                result_text = await execute_like_and_fetch_result(DEFAULT_UID)
                if MY_TELEGRAM_ID:
                    await user_client.send_message(
                        MY_TELEGRAM_ID,
                        f"🔔 **تقرير اللايك اليومي (5:00 فجراً):**\n\n{result_text}",
                    )
                await asyncio.sleep(61)
            except Exception as e:
                print(f"خطأ في التنفيذ التلقائي: {e}")
        await asyncio.sleep(30)


async def start_services():
    await user_client.start()
    if call_py:
        try:
            await call_py.start()
            print("تم تفعيل محرك المكالمات الصوتية PyTgCalls بنجاح!")
        except Exception as e:
            print(f"تنبيه: تعذر تشغيل PyTgCalls: {e}")
    print("تم تشغيل اليوزر بوت بنجاح تام عبر SESSION_STRING!")
    asyncio.create_task(daily_task())


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_services())
