import os
import asyncio
from fastapi import FastAPI
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from datetime import datetime, timezone, timedelta

# قراءة المتغيرات من راندر
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
TARGET_CHAT = os.environ.get("TARGET_CHAT", "")
MY_TELEGRAM_ID = int(os.environ.get("MY_TELEGRAM_ID", 0))
STICKER_ID = os.environ.get("STICKER_ID", "")

if TARGET_CHAT and TARGET_CHAT.lstrip("-").isdigit():
    TARGET_CHAT = int(TARGET_CHAT)

app = FastAPI()

@app.get("/")
def home():
    return {"status": "Mahdi Userbot is running securely!"}

user_client = TelegramClient(StringSession(SESSION_STRING) if SESSION_STRING else 'user_session', API_ID, API_HASH)

async def execute_like_and_fetch_result():
    try:
        sent_msg = await user_client.send_message(TARGET_CHAT, "/like me 11877711994")
        
        for _ in range(20):
            await asyncio.sleep(1)
            messages = await user_client.get_messages(TARGET_CHAT, limit=6, min_id=sent_msg.id)
            for msg in messages:
                if msg.text and ("UID" in msg.text or "NickName" in msg.text or "Added" in msg.text):
                    return f"📊 **نتيجة اللايك من القروب:**\n\n{msg.text}"
                    
        return "✅ تم إرسال أمر اللايك للقروب، ولكن لم يرد بوت اللايكات خلال المهلة المحددة."
    except Exception as e:
        return f"❌ خطأ أثناء تنفيذ أمر اللايك: {e}"

@user_client.on(events.NewMessage(outgoing=True, pattern=r'^/mahdi$'))
async def mahdi_menu(event):
    menu_text = (
        "👑 **قائمة أوامر يوزر بوت مهدي:**\n\n"
        "▫️ `/like` - تنفيذ أمر اللايك وجلب النتيجة فوراً.\n"
        "▫️ `/status` - التحقق من عمل السيرفر.\n"
        "▫️ `/mahdi` - إظهار هذه القائمة."
    )
    await event.edit(menu_text)

@user_client.on(events.NewMessage(outgoing=True, pattern=r'^/like$'))
async def manual_like(event):
    wait_msg = await event.edit("⏳ جاري إرسال أمر اللايك وانتظار النتيجة من القروب...")
    result = await execute_like_and_fetch_result()
    await wait_msg.edit(result)

@user_client.on(events.NewMessage(outgoing=True, pattern=r'^/status$'))
async def status_cmd(event):
    await event.edit("✅ اليوزر بوت يعمل بكفاءة تامة وآمن تماماً باستخدام جلسة الحساب الموثوقة.")

@user_client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def auto_reply(event):
    if event.sender_id == MY_TELEGRAM_ID or event.out:
        return
    reply_text = "أهلاً يا حلو 🤍\nأنا الحين ماني متصل، اترك رسالتك وإن شاء الله برد عليك ياقلبي 🫀"
    try:
        if STICKER_ID:
            await event.respond(reply_text, file=STICKER_ID)
        else:
            await event.respond(reply_text)
    except Exception as e:
        print(f"خطأ في الرد التلقائي: {e}")

async def daily_task():
    await asyncio.sleep(25)
    print("بدء نظام الجدولة اليومية لإرسال اللايك الساعة 5:00 فجراً...")
    while True:
        local_now = datetime.now(timezone(timedelta(hours=3)))
        if local_now.hour == 5 and local_now.minute == 0:
            try:
                result_text = await execute_like_and_fetch_result()
                if MY_TELEGRAM_ID:
                    await user_client.send_message(MY_TELEGRAM_ID, f"🔔 **تقرير اللايك اليومي (5:00 فجراً):**\n\n{result_text}")
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
