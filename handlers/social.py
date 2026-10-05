"""Modular handler module for ItzVanyaBot Ultimate.

Loaded after bot.py has initialized its shared runtime namespace. This keeps
existing handler behavior while separating feature code into maintainable files.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

async def persona(update, context):
    await update.message.reply_html(
        "💜 <b>Meet Vanya</b>\n\n"
        "I'm <b>Vanya</b>, a fictional AI character. I'm 22, from Jaipur, "
        "and I study design in Pune. I chat in casual Hinglish like a good friend.\n\n"
        "✨ Natural DM chat\n"
        "💬 Mention/reply-to chat in groups\n"
        "🧠 Short conversation memory\n"
        "⌨️ Natural typing feel\n"
        "😂 Warm, funny, slightly teasing replies\n"
        "🎮 Games + economy + social features\n\n"
        "<i>I'm an AI character, not a real human.</i>"
    )


# ───────────────────── complete advertised features ─────────────────────

async def rank(update, context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    xp = int(u.get("xp", 0))
    level = int(u.get("level", 1))
    await update.message.reply_html(
        f"⭐ <b>{html.escape(u.get('name','User'))}'s Rank</b>\n"
        f"XP: <b>{xp:,}</b>\nLevel: <b>{level}</b>\n"
        f"Next level: <b>{max(0, level*1000-xp):,} XP</b>"
    )

async def kill(update, context):
    target = await target_user(update)
    if not target or target.id == update.effective_user.id:
        await update.message.reply_text("Reply to another player: /kill &lt;amount&gt;")
        return
    try:
        amount = max(1, int(context.args[0]))
    except Exception:
        amount = 100
    me = await get_user(update.effective_user.id)
    victim = await get_user(target.id)
    if not victim:
        await ensure_user(target)
        victim = await get_user(target.id)
    amount = min(amount, int(victim.get("coins", 0)))
    if amount <= 0:
        await update.message.reply_text("That player has no coins to bounty. 😭")
        return
    if random.random() < 0.5:
        await add_coins(target.id, -amount)
        await add_coins(update.effective_user.id, amount)
        await users.update_one({"_id": update.effective_user.id}, {"$inc": {"kills": 1}})
        await update.message.reply_text(f"🎯 Fictional bounty won! +{amount:,} coins.")
    else:
        fine = min(100, int(me.get("coins", 0)))
        await add_coins(update.effective_user.id, -fine)
        await update.message.reply_text(f"💥 Bounty failed. You lost {fine:,} coins.")

async def revive(update, context):
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a player: /revive")
        return
    await ensure_user(target)
    await users.update_one({"_id": target.id}, {"$set": {"revived": True}})
    await update.message.reply_text(f"✨ {target.first_name or 'Player'} has been revived!")

async def topkill(update, context):
    cur = users.find().sort("kills", -1).limit(10)
    rows = []
    i = 1
    async for u in cur:
        rows.append(f"{i}. {html.escape(u.get('name','User'))} — {u.get('kills',0)}")
        i += 1
    await update.message.reply_html("🎯 <b>Top Assassins</b>\n\n" + ("\n".join(rows) or "No scores yet."))

async def marriage(update, context):
    target = await target_user(update) or update.effective_user
    await ensure_user(target)
    u = await get_user(target.id)
    partner = u.get("partner")
    if partner:
        p = await get_user(partner)
        pname = p.get("name", str(partner)) if p else str(partner)
        await update.message.reply_html(f"💕 <b>{html.escape(u.get('name','User'))}</b> is married to <b>{html.escape(pname)}</b>.")
    else:
        await update.message.reply_text("💔 Single for now.")

async def reject(update, context):
    u = await get_user(update.effective_user.id)
    if not u or not u.get("pending_proposal"):
        await update.message.reply_text("No pending proposal.")
        return
    await users.update_one({"_id": update.effective_user.id}, {"$unset": {"pending_proposal": ""}})
    await update.message.reply_text("💔 Proposal declined. No hard feelings.")

STAFF_COMMANDS = {
    "owner": "Open Owner/Sudo panel",
    "ownerpanel": "Open Owner/Sudo panel",
    "panel": "Open Owner/Sudo panel",
    "devpanel": "Open Owner/Sudo panel",
    "broadcast": "Broadcast to users, groups, or both",
    "addcoins": "Add coins by user ID",
    "removecoins": "Remove coins by user ID",
    "sudolist": "List sudo users",
    "auth": "Authorize current group",
    "unauth": "Unauthorize current group",
    "authlist": "List authorized groups",
    "stats": "View bot statistics",
    "revealgrid": "Reveal Wordgrid answer",
    "revealwordseek": "Reveal Wordseek answer",
    "addemoji": "Save premium custom emoji",
    "addsudo": "Add sudo user",
    "delsudo": "Remove sudo user",
    "blacklist": "Blacklist a user (Owner only)",
    "unblacklist": "Remove a user from blacklist (Owner only)",
}
OWNER_ONLY_COMMANDS = {"addsudo", "delsudo", "addemoji", "blacklist", "unblacklist"}
