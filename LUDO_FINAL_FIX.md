# Ludo final fix

This build replaces the previous Ludo board with a stable SVG board so home pockets, track, lanes and centre cannot overflow or stretch.

Gameplay rules enforced server-side:
- 2–4 players; bots are optional and never added automatically.
- Tokens stay in home until a 6 is rolled.
- After a roll, only legal tokens can be selected.
- A roll of 6 gives another turn.
- Moves cannot exceed the centre finish.
- Safe squares protect tokens; opponent tokens on capturable squares are sent home.
- Four finished tokens wins the match.
- Live WebSocket state synchronization, reconnect support, room invites and chat.

Recommended public URL variables remain:
- LUDO_WEBAPP_URL=https://avyranewup-production.up.railway.app/ludo
- UNO_WEBAPP_URL=https://avyranewup-production.up.railway.app/uno
- CHESS_WEBAPP_URL=https://avyranewup-production.up.railway.app/chess
