# Railway setup

Deploy this repository with the included Dockerfile.

IMPORTANT: Railway does not automatically create a `.env` file. Add environment variables in:
Railway -> Project -> Service -> Variables.

Minimum required:
BOT_TOKEN=your BotFather token

Recommended:
OWNER_ID=your Telegram numeric user ID
MONGO_URL=your MongoDB connection string
MONGO_DB=ItzVanyaBot

After saving Variables, trigger a new deployment/redeploy.

The bot now reads BOT_TOKEN from the Railway environment (and also supports TELEGRAM_BOT_TOKEN).
It no longer assumes that a physical `.env` file exists.

Never commit real bot tokens or database passwords to GitHub.
