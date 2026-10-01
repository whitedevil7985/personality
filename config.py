import os
from dotenv import load_dotenv

load_dotenv()

def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

# Railway and local .env are both supported.
TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or ""
).strip()

# MongoDB configuration.
# IMPORTANT: When MONGO_URL is supplied from Railway/Atlas, use it exactly as provided.
# Do not decode/re-encode the password because that can change valid characters such as '+'.
from urllib.parse import quote_plus

_raw_mongo_url = (
    os.getenv("MONGO_URL")
    or os.getenv("MONGODB_URI")
    or os.getenv("MONGO_URI")
    or ""
).strip()

if _raw_mongo_url:
    # Atlas gives a URI that is already correctly escaped. Keep it untouched.
    MONGO_URL = _raw_mongo_url
else:
    # Recommended alternative when the password contains special characters.
    mongo_user = os.getenv("MONGO_USER", "").strip()
    mongo_password = os.getenv("MONGO_PASSWORD", "")
    mongo_host = os.getenv("MONGO_HOST", "cluster0.0ydl89v.mongodb.net").strip()
    if mongo_user and mongo_password and mongo_host:
        MONGO_URL = (
            f"mongodb+srv://{quote_plus(mongo_user)}:{quote_plus(mongo_password)}"
            f"@{mongo_host}/?retryWrites=true&w=majority&appName=Cluster0"
        )
    else:
        MONGO_URL = ""

# Database name used by db.py. Keep a sensible default for Railway deployments.
MONGO_DB = os.getenv("MONGO_DB", "ItzVanyaBot").strip() or "ItzVanyaBot"

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DEVELOPER_NAME = os.getenv("DEVELOPER_NAME", "Developer")
OWNER_PROFILE_URL = os.getenv("OWNER_PROFILE_URL", "https://t.me/")
UPDATES_URL = os.getenv("UPDATES_URL", "https://t.me/")
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/")
LOGGER_CHAT_ID = int(os.getenv("LOGGER_CHAT_ID", "0"))

AI_GROUP_MODE = _bool("AI_GROUP_MODE", True)
AI_GROUP_REPLY_ALL = _bool("AI_GROUP_REPLY_ALL", False)
AI_DM_MODE = _bool("AI_DM_MODE", True)
AI_DISCLOSURE = _bool("AI_DISCLOSURE", False)
# Elite LLMs is OpenAI-compatible and uses /v1/chat/completions.
ELITE_LLM_API_KEY = os.getenv("ELITE_LLM_API_KEY", "").strip().strip('"').strip("'")
ELITE_LLM_BASE_URL = os.getenv("ELITE_LLM_BASE_URL", "https://elite-llms.vercel.app/v1").strip().rstrip("/")
ELITE_LLM_MODEL = os.getenv("ELITE_LLM_MODEL", "gpt-5.6-luna").strip().strip('"').strip("'")
# Fallback ChatGP API. The endpoint is OpenAI-unrelated and uses a simple prompt/response contract.
CHATGP_API_KEY = os.getenv("CHATGP_API_KEY", "").strip().strip('"').strip("'")
CHATGP_API_URL = os.getenv("CHATGP_API_URL", "https://chatgp-nine.vercel.app/api/chat").strip().rstrip("/")
CHATGP_TIMEOUT_SECONDS = float(os.getenv("CHATGP_TIMEOUT_SECONDS", "2.0"))
# Keep AI_MODEL for compatibility with older deployments.
AI_MODEL = os.getenv("AI_MODEL", "").strip() or ELITE_LLM_MODEL
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "30"))
MEMORY_ENABLED = _bool("MEMORY_ENABLED", True)
MAX_MEMORY = int(os.getenv("MAX_MEMORY", "30"))
MEMORY_DAYS = int(os.getenv("MEMORY_DAYS", "30"))

SUDO_IDS = {
    int(x.strip()) for x in os.getenv("SUDO_IDS", "").split(",")
    if x.strip().isdigit()
}

# Economy / progression
DAILY_MIN = int(os.getenv("DAILY_MIN", "250"))
DAILY_MAX = int(os.getenv("DAILY_MAX", "750"))
SPIN_COOLDOWN_HOURS = int(os.getenv("SPIN_COOLDOWN_HOURS", "24"))
QUEST_REWARD = int(os.getenv("QUEST_REWARD", "300"))
ACHIEVEMENT_REWARD = int(os.getenv("ACHIEVEMENT_REWARD", "250"))
