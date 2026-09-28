import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URL, MONGO_DB

if not MONGO_URL:
    raise RuntimeError("MONGO_URL is not configured. Set MONGO_URL in Railway Variables.")

client = AsyncIOMotorClient(
    MONGO_URL,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=10000,
)
db = client[MONGO_DB]
users = db.users
groups = db.groups
games = db.games
game_stats = db.game_stats

async def ensure_user(user):
    if not user:
        return
    await users.update_one(
        {"_id": user.id},
        {"$set": {"name": user.first_name or "User", "username": user.username},
         "$setOnInsert": {"coins": 1000, "xp": 0, "level": 1,
                          "warnings": 0, "protected_until": None,
                          "partner": None, "pending_proposal": None, "group_ids": [], "daily": None, "kills": 0, "chat_history": [], "memories": [], "memory": [], "ai_disclosure_sent": False, "kills": 0, "is_sudo": False, "revived": False, "mines_active": False, "mines_set": [], "mines_safe": [], "mines_bet": 0, "streak": 0, "last_active": None, "spin_at": None, "quest_day": None, "quest_progress": 0, "achievements": []}},
        upsert=True
    )

async def mark_started(user):
    if not user:
        return
    await users.update_one(
        {"_id": user.id},
        {"$set": {"name": user.first_name or "User", "username": user.username, "started": True, "started_at": datetime.now(timezone.utc)}},
        upsert=True
    )

async def track_group(chat):
    if not chat or chat.type == "private":
        return
    await groups.update_one(
        {"_id": chat.id},
        {"$set": {"title": chat.title or "Group", "type": chat.type, "last_seen": datetime.now(timezone.utc), "active": True},
         "$setOnInsert": {"couple_pairs": []}},
        upsert=True
    )

async def get_user(uid):
    return await users.find_one({"_id": uid})

async def add_coins(uid, amount):
    await users.update_one({"_id": uid}, {"$inc": {"coins": amount}}, upsert=True)

async def add_xp(uid, amount):
    u = await get_user(uid)
    if not u:
        return
    xp = int(u.get("xp", 0)) + amount
    level = 1 + xp // 1000
    await users.update_one({"_id": uid}, {"$set": {"xp": xp, "level": level}})
    return xp, level

async def top_users(limit=10):
    return users.find().sort("coins", -1).limit(limit)


async def record_game_result(uid, game, points=0, won=False, chat_id=None):
    """Store one completed game result for leaderboard aggregation."""
    if not uid or not game:
        return
    try:
        points = max(0, int(points))
    except (TypeError, ValueError):
        points = 0
    await game_stats.insert_one({
        "uid": int(uid),
        "game": str(game).upper(),
        "points": points,
        "wins": 1 if won else 0,
        "chat_id": int(chat_id) if chat_id is not None else None,
        "created_at": datetime.now(timezone.utc),
    })


async def get_game_leaderboard(game="ALL", scope="global", chat_id=None, since=None, limit=10):
    """Aggregate leaderboard points and wins for a period and scope."""
    match = {}
    if since is not None:
        match["created_at"] = {"$gte": since}
    if str(game).upper() != "ALL":
        match["game"] = str(game).upper()
    if str(scope).lower() == "group":
        if chat_id is None:
            return []
        match["chat_id"] = int(chat_id)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$uid",
            "points": {"$sum": "$points"},
            "wins": {"$sum": "$wins"},
            "games": {"$sum": 1},
        }},
        {"$sort": {"points": -1, "wins": -1, "games": -1, "_id": 1}},
        {"$limit": max(1, int(limit))},
    ]
    rows = []
    async for row in game_stats.aggregate(pipeline):
        user = await get_user(row["_id"])
        rows.append({
            "uid": row["_id"],
            "name": (user or {}).get("name") or f"User {row['_id']}",
            "points": int(row.get("points", 0)),
            "wins": int(row.get("wins", 0)),
            "games": int(row.get("games", 0)),
        })
    return rows
