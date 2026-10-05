import html
from datetime import datetime, timezone, timedelta
from db import ensure_user, get_user, add_coins, add_xp, users, get_user_lock
from config import SPIN_COOLDOWN_HOURS, QUEST_REWARD, ACHIEVEMENT_REWARD

async def _touch_streak(uid):
    now = datetime.now(timezone.utc)
    u = await get_user(uid)
    last = u.get("last_active") if u else None
    streak = int(u.get("streak", 0)) if u else 0
    if last:
        try:
            d = datetime.fromisoformat(last)
            delta = now.date() - d.date()
            if delta.days == 1:
                streak += 1
            elif delta.days > 1:
                streak = 1
        except Exception:
            streak = 1
    else:
        streak = 1
    await users.update_one({"_id": uid}, {"$set": {"streak": streak, "last_active": now.isoformat()}}, upsert=True)
    return streak

async def spin(update, context):
    await ensure_user(update.effective_user)
    uid = update.effective_user.id
    async with get_user_lock(uid):
        u = await get_user(uid)
        now = datetime.now(timezone.utc)
        last = u.get("spin_at")
        if last:
            try:
                remaining = timedelta(hours=SPIN_COOLDOWN_HOURS) - (now - datetime.fromisoformat(last))
                if remaining.total_seconds() > 0:
                    hours = int(remaining.total_seconds() // 3600)
                    mins = int(remaining.total_seconds() % 3600 // 60)
                    await update.message.reply_text(
                        f"🎡 Spin is cooling down. Try again in {hours}h {mins}m."
                    )
                    return
            except Exception:
                pass

        rewards = [(100, "💜"), (250, "✨"), (500, "💎"), (750, "🔥"), (1000, "👑")]
        amount, icon = rewards[__import__("random").randrange(len(rewards))]
        await add_coins(uid, amount)
        streak = await _touch_streak(uid)
        await users.update_one(
            {"_id": uid},
            {"$set": {"spin_at": now.isoformat()}},
        )

    await update.message.reply_text(
        f"🎡 {icon} <b>Daily Spin!</b>\n"
        f"You won <b>+{amount:,} coins</b>\n"
        f"🔥 Streak: <b>{streak}</b> day(s)",
        parse_mode="HTML",
    )

async def achievements(update, context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    unlocked = u.get("achievements", [])
    text = [
        "🏆 <b>Vanya Achievements</b>",
        "",
        f"💰 Rich — {'✅' if 'rich' in unlocked else '⬜'} Reach 5,000 coins",
        f"🎮 Gamer — {'✅' if 'gamer' in unlocked else '⬜'} Play a game",
        f"🔥 Streak — {'✅' if 'streak' in unlocked else '⬜'} Reach a 7-day streak",
        f"🧠 Memory — {'✅' if 'memory' in unlocked else '⬜'} Save a memory",
    ]
    await update.message.reply_html("\n".join(text))

async def quest(update, context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    now = datetime.now(timezone.utc).date().isoformat()
    if u.get("quest_day") != now:
        await users.update_one({"_id": update.effective_user.id}, {"$set": {"quest_day": now, "quest_progress": 0}})
        progress = 0
    else:
        progress = int(u.get("quest_progress", 0))
    await update.message.reply_html(
        "📜 <b>Daily Quest</b>\n\n"
        f"🎯 Send 3 messages/commands today: <b>{progress}/3</b>\n"
        f"🎁 Reward: <b>+{QUEST_REWARD:,} coins</b>\n\n"
        "Keep chatting/playing to progress."
    )

async def progress_quest(uid, amount=1):
    if not uid or amount <= 0:
        return

    async with get_user_lock(uid):
        u = await get_user(uid)
        if not u:
            return

        today = datetime.now(timezone.utc).date().isoformat()
        if u.get("quest_day") != today:
            progress = 0
            await users.update_one(
                {"_id": uid},
                {"$set": {"quest_day": today, "quest_progress": 0}},
            )
        else:
            progress = int(u.get("quest_progress", 0))

        if progress >= 3:
            return

        new_progress = min(3, progress + int(amount))
        await users.update_one(
            {"_id": uid},
            {"$set": {"quest_progress": new_progress}},
        )
        if progress < 3 and new_progress >= 3:
            await add_coins(uid, QUEST_REWARD)

