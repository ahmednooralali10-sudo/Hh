import os
import re
import time
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# قراءة المتغيرات من Render
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
TARGET_CHAT = os.environ.get("TARGET_CHAT", "")
MY_TELEGRAM_ID = int(os.environ.get("MY_TELEGRAM_ID", 0))
STICKER_ID = os.environ.get("STICKER_ID", "")

DEFAULT_UID = "11877711994"
DEFAULT_AFK_MSG = "أهلاً يا حلو 🤍\nأنا الحين ماني متصل، اترك رسالتك وإن شاء الله برد عليك ياقلبي 🫀"
KSA_TZ = timezone(timedelta(hours=3))

if TARGET_CHAT and TARGET_CHAT.lstrip("-").isdigit():
    TARGET_CHAT = int(TARGET_CHAT)

app = FastAPI()


@app.get("/")
def home():
    return {"status": "Mahdi Userbot v3 is running securely!"}


user_client = TelegramClient(
    StringSession(SESSION_STRING) if SESSION_STRING else "user_session",
    API_ID,
    API_HASH,
)

# حالة التشغيل والذاكرة المؤقتة
START_TIME = time.time()
AFK_ENABLED = True
DAILY_SCHED_ENABLED = True
SHORTCUTS_ENABLED = True
AFK_TEXT = DEFAULT_AFK_MSG
AFK_REPLIES_COUNT = 0
LIKE_RUNS_COUNT = 0
COMMANDS_USED_COUNT = 0
SHORTCUT_TRIGGERS_COUNT = 0
LAST_RESULT = "لم يتم تسجيل أي نتيجة لايك حتى الآن."
RESULT_HISTORY: list[str] = []
SHORTCUTS: dict[str, list[str]] = {}
NOTES: list[str] = []


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


# ==========================================
# دالة إرسال اللايك وانتظار النتيجة من القروب
# ==========================================
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
# القائمة الرئيسية الشاملة (/mahdi)
# ==========================================
@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/mahdi$"))
async def mahdi_menu(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    afk_state = "مفعل ✅" if AFK_ENABLED else "متوقف ⏸️"
    sched_state = "مفعل ✅" if DAILY_SCHED_ENABLED else "متوقف ⏸️"
    sa_state = "مفعل ✅" if SHORTCUTS_ENABLED else "متوقف ⏸️"
    menu_text = (
        "👑 **قائمة أوامر يوزر بوت مهدي (44 ميزة):**\n\n"
        "**⚡ الاختصارات الذكية:**\n"
        "• `/sa <اختصار> <نص>` — إضافة عبارة لاختصار (يدعم تعدد العبارات)\n"
        "• `/sa` أو `/salist` — عرض كل الاختصارات\n"
        "• `/sadel <اختصار>` — حذف اختصار | `/saclear` — مسح الكل\n"
        "• `/saon` و `/saoff` — تشغيل أو إيقاف الاختصارات\n\n"
        "**🎯 اللايكات والجدولة:**\n"
        f"• `/like` — إرسال للآيدي الافتراضي (`{DEFAULT_UID}`)\n"
        "• `/like <UID>` — إرسال لآيدي محدد\n"
        "• `/like2 <UID1> <UID2>` — إرسال متسلسل بفاصل آمن\n"
        "• `/repeat <1-5> [UID]` — تكرار آمن مع تهدئة\n"
        "• `/last` — آخر نتيجة | `/history` — سجل آخر 10 نتائج\n"
        "• `/clearhist` — مسح السجل المؤقت\n"
        "• `/sched` و `/sched on|off` — جدولة 5:00 فجراً\n\n"
        "**🤖 الرد التلقائي (AFK):**\n"
        "• `/afk` — تبديل | `/afkon` | `/afkoff`\n"
        "• `/afkmsg <نص>` — تخصيص رسالة AFK | `/afkreset` — استعادة الافتراضي\n"
        "• `/afkcount` — عدد الردود التلقائية\n\n"
        "**✉️ الرسائل والتحرير:**\n"
        "• `/say <نص>` و `/echo <نص>` — إرسال نص\n"
        "• `/del` (بالرد) — حذف رسالة\n"
        "• `/edit <نص>` (بالرد على رسالتك) — تعديل رسالة\n"
        "• `/pin` و `/unpin` (بالرد) — تثبيت / إلغاء تثبيت\n"
        "• `/copy` (بالرد) — نسخ نص رسالة\n\n"
        "**📝 الملاحظات والأدوات:**\n"
        "• `/note <نص>` | `/notes` | `/delnote <رقم>` | `/clearnotes`\n"
        "• `/id` | `/info [يوزر/آيدي]` | `/ping` | `/status` | `/stats` | `/time` | `/uuid`\n"
        "• `/calc <تعبير>` | `/rev <نص>` | `/upper <نص>` | `/lower <نص>` | `/len <نص>`\n\n"
        f"⚙️ **AFK:** {afk_state} | **الاختصارات:** {sa_state} | **5:00:** {sched_state}"
    )
    await event.edit(menu_text)


# ==========================================
# مجموعة الاختصارات الذكية (/sa)
# ==========================================
@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/sa(?:\s+(\S+)(?:\s+(.+))?)?$", flags=re.DOTALL))
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


# ==========================================
# مجموعة اللايكات والجدولة
# ==========================================
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


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/sched(?:\s+(on|off))?$", flags=re.IGNORECASE))
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


# ==========================================
# مجموعة الرد التلقائي AFK
# ==========================================
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


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/afkmsg\s+(.+)$", flags=re.DOTALL))
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


# ==========================================
# مجموعة الرسائل والتحرير
# ==========================================
@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/say\s+(.+)$", flags=re.DOTALL))
async def say_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(event.pattern_match.group(1))


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/echo\s+(.+)$", flags=re.DOTALL))
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


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/edit\s+(.+)$", flags=re.DOTALL))
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


# ==========================================
# مجموعة الملاحظات والأدوات والحالة
# ==========================================
@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/note\s+(.+)$", flags=re.DOTALL))
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
    text = (
        "✅ **اليوزر بوت يعمل بكفاءة تامة**\n"
        f"⏱️ **مدة التشغيل:** `{format_uptime()}`\n"
        f"🤖 **الرد التلقائي:** {afk_state}\n"
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


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/calc\s+(.+)$"))
async def calc_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(safe_calc(event.pattern_match.group(1)))


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/rev\s+(.+)$", flags=re.DOTALL))
async def rev_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    txt = event.pattern_match.group(1)
    await event.edit(f"🔁 **النص معكوساً:**\n{txt[::-1]}")


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/upper\s+(.+)$", flags=re.DOTALL))
async def upper_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(event.pattern_match.group(1).upper())


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/lower\s+(.+)$", flags=re.DOTALL))
async def lower_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    await event.edit(event.pattern_match.group(1).lower())


@user_client.on(events.NewMessage(outgoing=True, pattern=r"^/len\s+(.+)$", flags=re.DOTALL))
async def len_cmd(event):
    global COMMANDS_USED_COUNT
    COMMANDS_USED_COUNT += 1
    txt = event.pattern_match.group(1)
    words = len(txt.split())
    chars = len(txt)
    await event.edit(f"📏 **طول النص:** `{chars}` حرف | `{words}` كلمة")


# ==========================================
# معالج التوسيع التلقائي للاختصارات عند إرسالها لحالها
# ==========================================
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


# ==========================================
# الرد التلقائي على الخاص (AFK)
# ==========================================
@user_client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def auto_reply(event):
    global AFK_REPLIES_COUNT
    if not AFK_ENABLED:
        return
    if event.sender_id == MY_TELEGRAM_ID or event.out:
        return
    try:
        if STICKER_ID:
            await event.respond(AFK_TEXT, file=STICKER_ID)
        else:
            await event.respond(AFK_TEXT)
        AFK_REPLIES_COUNT += 1
    except Exception as e:
        print(f"خطأ في الرد التلقائي: {e}")


# ==========================================
# الجدولة اليومية الساعة 5:00 فجراً
# ==========================================
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
    print("تم تشغيل اليوزر بوت بنجاح تام عبر SESSION_STRING!")
    asyncio.create_task(daily_task())


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_services())
