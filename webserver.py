import os
import json
import random
import string
import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote
from aiohttp import web, WSMsgType
from db import users, ensure_user, add_coins, add_xp, record_game_result, game_stats
try:
    import chess as chesslib
except Exception:
    chesslib = None

BASE = Path(__file__).resolve().parent
WEB = BASE / 'webapp'
ROOMS = {}
CHESS_ROOMS = {}
ROOM_LOCK = asyncio.Lock()
CHESS_LOCK = asyncio.Lock()
KINGDOM_ROOMS = {}
KINGDOM_LOCK = asyncio.Lock()
COLORS = ['red', 'green', 'yellow', 'blue']
COLOR_NAMES = {'red':'RED','green':'GREEN','yellow':'YELLOW','blue':'BLUE'}


def new_code():
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(random.choice(alphabet) for _ in range(6))
        if code not in ROOMS and code not in CHESS_ROOMS and code not in KINGDOM_ROOMS:
            return code


def request_group_id(request):
    try:
        value = int(request.query.get('gc', '0') or 0)
        return value if value else None
    except (TypeError, ValueError):
        return None


def new_room(game='ludo'):
    return {
        'code': None, 'game': game, 'players': [], 'started': False, 'turn': 0,
        'positions': {}, 'winner': None, 'last_roll': 0, 'created': time.time(),
        'updated': time.time(), 'chat': [], 'pending_roll': 0, 'movable': [], 'spectators': [], 'ended': False
    }


def create_kingdom_join_token(room_code, user_id, ttl=None):
    """Create a signed room token bound to one Telegram user ID."""
    room_code = str(room_code or "").upper().strip()
    uid = int(user_id)
    ttl = int(ttl or os.getenv("KINGDOM_JOIN_TOKEN_TTL_SECONDS", "21600"))
    expires = int(time.time()) + max(300, ttl)
    secret = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").encode()
    if not secret or not room_code:
        return ""
    payload = f"{room_code}:{uid}:{expires}"
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{uid}.{expires}.{signature}"


def verify_kingdom_join_token(room_code, token):
    """Verify a signed Kingdom Wars token and return its Telegram user ID."""
    room_code = str(room_code or "").upper().strip()
    try:
        uid_s, exp_s, signature = str(token or "").split(".", 2)
        uid = int(uid_s)
        expires = int(exp_s)
    except (TypeError, ValueError):
        return None
    if not room_code or time.time() > expires:
        return None
    secret = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").encode()
    if not secret:
        return None
    payload = f"{room_code}:{uid}:{expires}"
    expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return uid if hmac.compare_digest(expected, signature) else None


def verify_telegram_init_data(init_data: str):
    """Validate Telegram Mini App initData using Telegram's HMAC format."""
    if not init_data:
        return None
    try:
        pairs = parse_qsl(str(init_data), keep_blank_values=True)
        data = dict(pairs)
        received = data.pop('hash', '')
        if not received:
            return None

        bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN') or ''
        if not bot_token:
            return None

        check = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
        secret = hmac.new(
            b'WebAppData',
            bot_token.encode(),
            hashlib.sha256,
        ).digest()
        digest = hmac.new(
            secret,
            check.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(digest, received):
            return None

        auth_date = int(data.get('auth_date', '0') or 0)
        if auth_date and time.time() - auth_date > 86400:
            return None

        user = json.loads(data.get('user', '{}'))
        return user if user.get('id') is not None else None
    except Exception:
        return None


# ---------------- LUDO ----------------

def player_public(p):
    return {k: p[k] for k in ('id','name','color','bot','connected')}


def ludo_state(room):
    return {
        'type': 'state',
        'room': room['code'],
        'started': room['started'],
        'turn': room['turn'],
        'winner': room['winner'],
        'last_roll': room['last_roll'],
        'pending_roll': room.get('pending_roll', 0),
        'movable': list(room.get('movable', [])),
        'players': [player_public(p) for p in room['players']],
        'positions': {str(k): list(v) for k, v in room['positions'].items()},
    }


async def broadcast_ludo(room, extra=None):
    payload = ludo_state(room)
    if extra:
        payload.update(extra)
    msg = json.dumps(payload, separators=(',', ':'))
    dead = []
    for p in room['players']:
        ws = p.get('ws')
        if ws and not ws.closed:
            try:
                await ws.send_str(msg)
            except Exception:
                dead.append(p)
    for p in dead:
        p['ws'] = None
        p['connected'] = False
    live_specs = []
    for ws in room.get('spectators', []):
        if ws and not ws.closed:
            try:
                await ws.send_str(msg)
                live_specs.append(ws)
            except Exception:
                pass
    room['spectators'] = live_specs


def find_player(room, pid):
    return next((p for p in room['players'] if p['id'] == pid), None)


def current_player(room):
    if not room['players']:
        return None
    return room['players'][room['turn'] % len(room['players'])]


# Ludo rules mirror the supplied source implementation:
# progress -1 = base, 0..51 = outer track, 52..56 = five coloured home-lane
# cells, and 57 = centre finish.
LUDO_PATH_LEN = 52
LUDO_PATH = [
    (6,1),(6,2),(6,3),(6,4),(6,5),
    (5,6),(4,6),(3,6),(2,6),(1,6),(0,6),
    (0,7),(0,8),
    (1,8),(2,8),(3,8),(4,8),(5,8),
    (6,9),(6,10),(6,11),(6,12),(6,13),(6,14),
    (7,14),(8,14),
    (8,13),(8,12),(8,11),(8,10),(8,9),
    (9,8),(10,8),(11,8),(12,8),(13,8),(14,8),
    (14,7),(14,6),
    (13,6),(12,6),(11,6),(10,6),(9,6),
    (8,5),(8,4),(8,3),(8,2),(8,1),(8,0),
    (7,0),(6,0)
]
LUDO_START = {'red': 0, 'green': 13, 'yellow': 26, 'blue': 39}
LUDO_LANES = {
    # Five coloured home-lane boxes per colour; the central 3x3 finish
    # area begins immediately after these lanes.
    'red': [(7,1),(7,2),(7,3),(7,4),(7,5)],
    'green': [(1,7),(2,7),(3,7),(4,7),(5,7)],
    'yellow': [(7,13),(7,12),(7,11),(7,10),(7,9)],
    'blue': [(13,7),(12,7),(11,7),(10,7),(9,7)],
}
LUDO_SAFE = {0, 8, 13, 21, 26, 34, 39, 47}
LUDO_FINISH = 57
LUDO_HOME = -1


def ludo_global_index(player, progress):
    return (LUDO_START[player['color']] + progress) % LUDO_PATH_LEN


def legal_ludo_moves(room, player, roll):
    arr = room['positions'].setdefault(player['id'], [LUDO_HOME, LUDO_HOME, LUDO_HOME, LUDO_HOME])
    moves = []
    for i, pos in enumerate(arr):
        if pos == LUDO_FINISH:
            continue
        if pos == LUDO_HOME:
            # A token can leave home only on a six.
            if roll == 6:
                moves.append(i)
        elif pos + roll <= LUDO_FINISH:
            moves.append(i)
    return moves


def ludo_capture(room, player, newpos):
    if newpos < 0 or newpos > 51:
        return []
    target = ludo_global_index(player, newpos)
    if target in LUDO_SAFE:
        return []
    captured = []
    for other in room['players']:
        if other['id'] == player['id']:
            continue
        arr = room['positions'].get(other['id'], [])
        for i, pos in enumerate(arr):
            if 0 <= pos <= 51 and ludo_global_index(other, pos) == target:
                arr[i] = LUDO_HOME
                captured.append({'player': other['id'], 'token': i})
    return captured


def apply_ludo_move(room, player, token, roll):
    arr = room['positions'].setdefault(player['id'], [LUDO_HOME] * 4)
    if not isinstance(token, int) or token < 0 or token >= 4:
        return False, None, []
    pos = arr[token]
    if pos == LUDO_FINISH:
        return False, None, []
    if pos == LUDO_HOME:
        if roll != 6:
            return False, None, []
        newpos = 0
    else:
        newpos = pos + roll
        if newpos > LUDO_FINISH:
            return False, None, []
    arr[token] = newpos
    captured = ludo_capture(room, player, newpos)
    if all(x == LUDO_FINISH for x in arr):
        room['winner'] = player['id']
    return True, newpos, captured


def ludo_advance_turn(room):
    if room['players']:
        room['turn'] = (room['turn'] + 1) % len(room['players'])


async def _ludo_award(room):
    """Pay out a finished Ludo match once and record leaderboard points."""
    if room.get('payout_done') or not room.get('winner'):
        return
    room['payout_done'] = True

    winner_id = str(room.get('winner'))
    for player in room.get('players', []):
        uid = player.get('id')
        try:
            numeric_uid = int(uid)
        except (TypeError, ValueError):
            # Guest/browser-only seats do not have a Telegram balance.
            continue

        try:
            if str(uid) == winner_id:
                await add_coins(numeric_uid, 500)
                await add_xp(numeric_uid, 100)
                await record_game_result(
                    numeric_uid, 'LUDO', points=500, won=True,
                    chat_id=room.get('group_id'),
                )
            else:
                await record_game_result(
                    numeric_uid, 'LUDO', points=100, won=False,
                    chat_id=room.get('group_id'),
                )
        except Exception as exc:
            print(f"[Ludo][Reward] {type(exc).__name__}: {exc}")


def ludo_reset_roll(room):
    room['pending_roll'] = 0
    room['movable'] = []


async def maybe_ludo_bot_turn(room):
    # One task per room keeps rapid state updates from spawning duplicate bot turns.
    await asyncio.sleep(0.65)
    if room.get('ended') or not room['started'] or room['winner'] or room.get('pending_roll'):
        return
    p = current_player(room)
    if not p or not p.get('bot'):
        return

    roll = random.randint(1, 6)
    room['last_roll'] = roll
    room['pending_roll'] = roll
    room['movable'] = legal_ludo_moves(room, p, roll)
    room['updated'] = time.time()
    await broadcast_ludo(room, {'event': 'roll', 'player': p['id'], 'result': 'choose_move', 'roll': roll})
    await asyncio.sleep(0.85)

    if not room['started'] or room['winner'] or room.get('pending_roll') != roll:
        return
    if not room['movable']:
        ludo_reset_roll(room)
        # A six still gives another roll, even when there is no legal move.
        if roll != 6:
            ludo_advance_turn(room)
        room['updated'] = time.time()
        await broadcast_ludo(room, {'event': 'no_move', 'player': p['id'], 'roll': roll})
        if current_player(room) and current_player(room).get('bot'):
            asyncio.create_task(maybe_ludo_bot_turn(room))
        return

    token = random.choice(room['movable'])
    ok, newpos, captured = apply_ludo_move(room, p, token, roll)
    if not ok:
        ludo_reset_roll(room)
        if roll != 6:
            ludo_advance_turn(room)
        room['updated'] = time.time()
        await broadcast_ludo(room, {'event': 'error', 'message': 'Bot move was rejected'})
        return

    ludo_reset_roll(room)
    # A capture grants the bot/player another turn, just like rolling a six.
    if not room['winner'] and roll != 6 and not captured:
        ludo_advance_turn(room)
    room['updated'] = time.time()
    await broadcast_ludo(room, {
        'event': 'move', 'player': p['id'], 'token': token, 'newpos': newpos,
        'captured': captured, 'roll': roll,
    })
    if room.get('winner'):
        await _ludo_award(room)
        await broadcast_ludo(room, {
            'event': 'winner',
            'winner': room.get('winner'),
            'winner_name': p.get('name') or 'Player',
            'reward_coins': 500,
            'reward_points': 500,
        })
    if room['started'] and not room['winner'] and current_player(room) and current_player(room).get('bot'):
        asyncio.create_task(maybe_ludo_bot_turn(room))


async def create_ludo_room(request):
    async with ROOM_LOCK:
        code = new_code()
        room = new_room('ludo')
        room['code'] = code
        room['group_id'] = request_group_id(request)
        room['positions'] = {}
        room['pending_roll'] = 0
        room['movable'] = []
        ROOMS['L:' + code] = room
    return web.json_response({'ok': True, 'room': code})


async def ludo_page(request):
    return web.FileResponse(WEB / 'ludo.html')


async def ludo_ws(request):
    code = request.match_info['code'].upper()
    room = ROOMS.get('L:' + code)
    if not room:
        return web.json_response({'ok': False, 'error': 'Room not found'}, status=404)

    ws = web.WebSocketResponse(heartbeat=25, max_msg_size=64 * 1024)
    await ws.prepare(request)
    tg_user = verify_telegram_init_data(request.query.get('initData', ''))
    client_id = (request.query.get('cid') or '').strip()
    client_id = ''.join(ch for ch in client_id if ch.isalnum() or ch in '_-')[:80]
    session_id = str(tg_user['id']) if tg_user else (('guest-' + client_id) if client_id else 'guest-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12)))

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except Exception:
                continue
            typ = data.get('type')

            if typ == 'join':
                name = (data.get('name') or (tg_user or {}).get('first_name') or 'Player').strip()[:32] or 'Player'
                wanted = data.get('color') if data.get('color') in COLORS else None
                p = find_player(room, session_id)
                spectator = False
                if not p:
                    if room['started']:
                        spectator = True
                        room.setdefault('spectators', []).append(ws)
                    else:
                        if len(room['players']) >= 4:
                            await ws.send_json({'type': 'error', 'message': 'Room is full'})
                            continue
                        used = {x['color'] for x in room['players']}
                        color = wanted if wanted and wanted not in used else next((c for c in COLORS if c not in used), None)
                        if not color:
                            await ws.send_json({'type': 'error', 'message': 'No color seat is available'})
                            continue
                        p = {'id': session_id, 'name': name, 'color': color, 'bot': False, 'connected': True, 'ws': ws}
                        room['players'].append(p)
                        room['positions'][session_id] = [LUDO_HOME, LUDO_HOME, LUDO_HOME, LUDO_HOME]
                else:
                    p['name'] = name
                    p['connected'] = True
                    p['ws'] = ws
                room['updated'] = time.time()
                personal = ludo_state(room)
                personal['you'] = session_id
                personal['spectator'] = spectator
                if spectator:
                    await ws.send_str(json.dumps(personal, separators=(',', ':')))
                else:
                    await broadcast_ludo(room, {'event': 'joined', 'player': session_id})
                    await ws.send_str(json.dumps(personal, separators=(',', ':')))

            elif typ == 'color':
                p = find_player(room, session_id)
                color = data.get('color')
                if not p or room['started'] or color not in COLORS:
                    continue
                if any(x['color'] == color and x['id'] != session_id for x in room['players']):
                    await ws.send_json({'type': 'error', 'message': 'That color is already taken'})
                    continue
                p['color'] = color
                room['updated'] = time.time()
                await broadcast_ludo(room, {'event': 'color', 'player': session_id})

            elif typ == 'add_bot':
                if room['started'] or len(room['players']) >= 4:
                    continue
                used = {x['color'] for x in room['players']}
                color = next((c for c in COLORS if c not in used), None)
                if color:
                    bid = 'bot-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
                    bot_no = sum(1 for x in room['players'] if x.get('bot')) + 1
                    p = {'id': bid, 'name': f'Bot {bot_no}', 'color': color, 'bot': True, 'connected': True, 'ws': None}
                    room['players'].append(p)
                    room['positions'][bid] = [LUDO_HOME, LUDO_HOME, LUDO_HOME, LUDO_HOME]
                    room['updated'] = time.time()
                    await broadcast_ludo(room, {'event': 'joined', 'player': bid})

            elif typ == 'start':
                if room['started'] or room['winner']:
                    continue
                if len(room['players']) < 2:
                    await ws.send_json({'type': 'error', 'message': 'At least 2 players are needed'})
                    continue
                room['started'] = True
                room['winner'] = None
                room['turn'] = 0
                room['last_roll'] = 0
                room['payout_done'] = False
                ludo_reset_roll(room)
                room['updated'] = time.time()
                await broadcast_ludo(room, {'event': 'started'})
                if current_player(room) and current_player(room).get('bot'):
                    asyncio.create_task(maybe_ludo_bot_turn(room))

            elif typ == 'roll':
                if not room['started'] or room['winner'] or room.get('pending_roll'):
                    continue
                p = find_player(room, session_id)
                cur = current_player(room)
                if not p or not cur or cur['id'] != session_id:
                    await ws.send_json({'type': 'error', 'message': 'Wait for your turn'})
                    continue

                roll = random.randint(1, 6)
                room['last_roll'] = roll
                room['pending_roll'] = roll
                room['movable'] = legal_ludo_moves(room, p, roll)
                room['updated'] = time.time()

                if not room['movable']:
                    # On 1–5 the turn changes. On 6 the same player may roll again.
                    ludo_reset_roll(room)
                    if roll != 6:
                        ludo_advance_turn(room)
                    room['updated'] = time.time()
                    await broadcast_ludo(room, {'event': 'no_move', 'player': p['id'], 'roll': roll})
                    if current_player(room) and current_player(room).get('bot'):
                        asyncio.create_task(maybe_ludo_bot_turn(room))
                else:
                    await broadcast_ludo(room, {'event': 'roll', 'player': p['id'], 'roll': roll, 'result': 'choose_move'})

            elif typ == 'move':
                if not room['started'] or room['winner'] or not room.get('pending_roll'):
                    continue
                p = find_player(room, session_id)
                cur = current_player(room)
                token = data.get('token')
                if not p or not cur or cur['id'] != session_id:
                    await ws.send_json({'type': 'error', 'message': 'Wait for your turn'})
                    continue
                if not isinstance(token, int) or token not in room.get('movable', []):
                    await ws.send_json({'type': 'error', 'message': 'Choose a highlighted token'})
                    continue

                roll = int(room['pending_roll'])
                ok, newpos, captured = apply_ludo_move(room, p, token, roll)
                if not ok:
                    await ws.send_json({'type': 'error', 'message': 'That token cannot move'})
                    continue

                ludo_reset_roll(room)
                # Capturing an opponent's token grants an extra turn, even
                # when the dice roll was not a six.
                if not room['winner'] and roll != 6 and not captured:
                    ludo_advance_turn(room)
                room['updated'] = time.time()
                await broadcast_ludo(room, {
                    'event': 'move', 'player': p['id'], 'token': token, 'newpos': newpos,
                    'captured': captured, 'roll': roll,
                })
                if room.get('winner'):
                    await _ludo_award(room)
                    await broadcast_ludo(room, {
                        'event': 'winner',
                        'winner': room.get('winner'),
                        'winner_name': p.get('name') or 'Player',
                        'reward_coins': 500,
                        'reward_points': 500,
                    })
                if room['started'] and not room['winner'] and current_player(room) and current_player(room).get('bot'):
                    asyncio.create_task(maybe_ludo_bot_turn(room))

            elif typ == 'chat':
                p = find_player(room, session_id)
                txt = (data.get('text') or '').strip()[:180]
                if p and txt:
                    room['chat'].append({'name': p['name'], 'text': txt})
                    room['chat'] = room['chat'][-30:]
                    await broadcast_ludo(room, {'event': 'chat', 'name': p['name'], 'text': txt})
    finally:
        p = find_player(room, session_id)
        if p and p.get('ws') is ws:
            p['connected'] = False
            p['ws'] = None
            room['updated'] = time.time()
            await broadcast_ludo(room, {'event': 'left', 'player': session_id})
        else:
            room['spectators'] = [x for x in room.get('spectators', []) if x is not ws]
    return ws


# ---------------- KINGDOM WARS ----------------

def kingdom_player_public(p, detailed=False):
    k=p.get('kingdom',{})
    data={
        'id':p['id'],'name':p.get('name') or 'Player','connected':bool(p.get('connected')),
        'kingdom':{
            'level':int(k.get('level',1)),
            'territory':int(k.get('territory',25)),
            'defense':int(k.get('defense',30)),
        }
    }
    if detailed:
        data['kingdom']={
            'gold':int(k.get('gold',500)),'food':int(k.get('food',220)),
            'wood':int(k.get('wood',180)),'stone':int(k.get('stone',140)),
            'army':int(k.get('army',80)),'population':int(k.get('population',120)),
            'level':int(k.get('level',1)),'territory':int(k.get('territory',25)),
            'defense':int(k.get('defense',30)),'buildings':int(k.get('buildings',3)),
            'wins':int(k.get('wins',0)),'losses':int(k.get('losses',0)),
        }
    return data

def new_kingdom_room(code=None, group_id=None):
    return {
        'code':code,'game':'kingdom','players':[],'started':False,'ended':False,
        'turn':0,'turn_started':0,'winner':None,'created':time.time(),
        'updated':time.time(),'group_id':group_id,'payout_done':False,'timer_task':None
    }

def kingdom_snapshot(room, you=None):
    players=[]
    for p in room['players']:
        players.append(kingdom_player_public(p, detailed=(p['id']==you)))
    turn_player=room['players'][room['turn']]['id'] if room['players'] and room['started'] and room['turn'] < len(room['players']) else None
    left=max(0,45-int(time.time()-room.get('turn_started',time.time()))) if room['started'] and not room['ended'] else 45
    me=next((kingdom_player_public(p, detailed=True)['kingdom'] for p in room['players'] if p['id']==you),{})
    return {
        'type':'state','room':room['code'],'started':room['started'],'ended':room['ended'],
        'turnPlayer':turn_player,'turnLeft':left,'winner':room['winner'],
        'players':players,'you':you,'you_kingdom':me,
    }

async def broadcast_kingdom(room, event='state', message=None, meta=None):
    sockets=[]
    for p in room['players']:
        ws=p.get('ws')
        if ws and not ws.closed: sockets.append((ws,p['id']))
    for ws,pid in sockets:
        try:
            payload=kingdom_snapshot(room,pid)
            if event=='event':
                payload={'type':'event','message':message or 'The realm changed.','state':kingdom_snapshot(room,pid),
                         'you':pid,'meta':meta or {}}
            elif event=='game_over':
                winner=next((p for p in room['players'] if p['id']==room.get('winner')),None)
                payload={'type':'game_over','winnerName':winner.get('name') if winner else 'A ruler',
                         'message':message or 'The crown has been claimed.','state':kingdom_snapshot(room,pid),'you':pid}
            await ws.send_str(json.dumps(payload,separators=(',',':')))
        except Exception:
            pass

async def create_kingdom_room_for_group(group_id=None):
    async with KINGDOM_LOCK:
        code=new_code()
        room=new_kingdom_room(code,group_id)
        KINGDOM_ROOMS[code]=room
        return code

def _kingdom_find(room,pid):
    return next((p for p in room['players'] if p['id']==pid),None)

def _kingdom_next(room):
    if room['players']:
        room['turn']=(room['turn']+1)%len(room['players'])
        room['turn_started']=time.time()
        room['updated']=time.time()

async def _kingdom_award(room):
    if room.get('payout_done') or not room.get('winner'):
        return
    room['payout_done']=True
    for p in room['players']:
        uid=p['id']
        try:
            numeric_uid=int(uid)
        except (TypeError,ValueError):
            continue
        try:
            is_winner = str(uid)==str(room.get('winner')) or numeric_uid==int(room.get('winner'))
        except (TypeError,ValueError):
            is_winner = False
        try:
            if is_winner:
                await add_coins(numeric_uid,500); await add_xp(numeric_uid,100)
                await record_game_result(numeric_uid,'KINGDOMWARS',500,True,room.get('group_id'))
            else:
                await add_coins(numeric_uid,100); await add_xp(numeric_uid,25)
                await record_game_result(numeric_uid,'KINGDOMWARS',100,False,room.get('group_id'))
        except Exception:
            pass

async def _kingdom_end(room,winner_id,message):
    room['winner']=winner_id; room['ended']=True; room['started']=False; room['updated']=time.time()
    if room.get('timer_task') and not room['timer_task'].done():
        room['timer_task'].cancel()
    await _kingdom_award(room)
    await broadcast_kingdom(room,'game_over',message)

async def _kingdom_timer(room):
    try:
        while room in KINGDOM_ROOMS.values() and not room.get('ended'):
            await asyncio.sleep(1)
            if not room.get('started') or not room.get('players'): continue
            if time.time()-room.get('turn_started',time.time())>=45:
                p=room['players'][room['turn']]
                _kingdom_next(room)
                await broadcast_kingdom(
                    room,'event',
                    f"⏱️ {p.get('name','Ruler')}'s turn expired. The crown passes on.",
                    {'kind':'turn_expired','actorId':p.get('id'),'actorName':p.get('name','Ruler')}
                )
    except asyncio.CancelledError:
        return

def _kingdom_start_if_ready(room):
    if not room['started'] and len(room['players'])>=2:
        room['started']=True; room['ended']=False; room['turn']=0; room['turn_started']=time.time(); room['updated']=time.time()
        task=asyncio.create_task(_kingdom_timer(room)); room['timer_task']=task
        return True
    return False

def _kingdom_action(room,p,action,target_id=None):
    k=p['kingdom']; action=(action or '').lower()
    if not room.get('players') or room.get('turn',0) >= len(room['players']):
        return False,'The battle state is not ready yet.'
    if room['players'][room['turn']]['id']!=p['id']:
        return False,'Wait for your turn.'
    if action=='farm':
        k['food']+=60; k['gold']+=10
        return True,'🌾 Farms produced +60 food and +10 gold.'
    if action=='wood':
        k['wood']+=55; k['gold']+=8
        return True,'🪵 Forests produced +55 wood and +8 gold.'
    if action=='stone':
        k['stone']+=45
        return True,'⛏ Quarries produced +45 stone.'
    if action=='build':
        if k['gold']<120 or k['wood']<60 or k['stone']<40: return False,'Need 120 gold, 60 wood and 40 stone to build.'
        k['gold']-=120; k['wood']-=60; k['stone']-=40; k['buildings']+=1; k['level']=1+(k['buildings']-3)//3; k['territory']+=2; k['defense']+=4
        return True,f"🏗️ Capital upgraded to level {k['level']}."
    if action=='recruit':
        if k['gold']<70 or k['food']<35: return False,'Need 70 gold and 35 food to recruit.'
        k['gold']-=70; k['food']-=35; k['army']+=30; k['population']+=10
        return True,'⚔️ Recruited 30 soldiers.'
    if action=='fortify':
        if k['gold']<50 or k['stone']<30: return False,'Need 50 gold and 30 stone to fortify.'
        k['gold']-=50; k['stone']-=30; k['defense']+=18
        return True,'🛡️ Walls strengthened by +18 defense.'
    if action=='scout':
        rivals=[x for x in room['players'] if x['id']!=p['id']]
        if not rivals: return False,'No rival kingdom to scout.'
        weakest=min(rivals,key=lambda x:x['kingdom']['defense'])
        return True,f"🔭 Scout report: {weakest['name']} has {weakest['kingdom']['defense']} defense and {weakest['kingdom']['territory']} land."
    if action=='attack':
        rivals=[x for x in room['players'] if x['id']!=p['id']]
        if not rivals: return False,'No rival kingdom to attack.'
        target=_kingdom_find(room,target_id) or rivals[0]
        if target['id']==p['id']: return False,'Choose a rival kingdom.'
        if k['army']<30: return False,'Need at least 30 soldiers to attack.'
        import random as _random
        attack_power=int(k['army']*_random.uniform(.82,1.18))+k['level']*8
        defense_power=int(target['kingdom']['defense']*_random.uniform(.86,1.14))
        k['army']=max(0,k['army']-25)
        target['kingdom']['army']=max(0,target['kingdom']['army']-10)
        if attack_power>=defense_power:
            target['kingdom']['territory']=max(8,target['kingdom']['territory']-7)
            k['territory']+=7; k['wins']+=1; target['kingdom']['losses']+=1
            k['gold']+=120; target['kingdom']['gold']=max(0,target['kingdom']['gold']-80)
            return True,f"🔥 {p['name']} captured 7 land from {target['name']}!"
        k['defense']=max(10,k['defense']-4); target['wins']+=1; k['losses']+=1
        return True,f"🛡️ {target['name']} repelled the attack. The invader lost troops."
    if action=='end_turn':
        return True,'⏭️ Turn ended.'
    return False,'Unknown command.'

async def create_kingdom_room(request):
    # A web-created Kingdom Wars room must have a verified Telegram identity.
    # Group-created rooms use the bot command/callback flow below.
    tg_user=verify_telegram_init_data(request.query.get('initData',''))
    if not tg_user:
        return web.json_response(
            {'ok':False,'error':'Telegram verification required.'},
            status=401,
        )
    gid=request_group_id(request)
    code=await create_kingdom_room_for_group(gid)
    return web.json_response({'ok':True,'room':code})

async def kingdom_page(request):
    return web.FileResponse(WEB/'kingdom_wars.html')

async def kingdom_ws(request):
    code=request.match_info['code'].upper()
    room=KINGDOM_ROOMS.get(code)
    if not room: return web.json_response({'ok':False,'error':'Room not found'},status=404)
    ws=web.WebSocketResponse(heartbeat=25,max_msg_size=64*1024)
    await ws.prepare(request)
    tg_user=verify_telegram_init_data(request.query.get('initData',''))
    token_uid=verify_kingdom_join_token(code,request.query.get('token',''))
    if token_uid is None and tg_user is None:
        await ws.send_json({'type':'error','message':'Telegram verification required. Open the Join button from Vanya.'})
        await ws.close()
        return ws
    if token_uid is not None and tg_user is not None and int(tg_user.get('id')) != int(token_uid):
        await ws.send_json({'type':'error','message':'Telegram account verification mismatch.'})
        await ws.close()
        return ws
    # A signed room token can authenticate a player even when Telegram's
    # Mini App initData is absent (for example when the link originated in a
    # group). This token is cryptographically bound to exactly one Telegram ID.
    verified_user_id=int(token_uid if token_uid is not None else tg_user['id'])
    session_id=str(verified_user_id)
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT: continue
            try: data=json.loads(msg.data)
            except Exception: continue
            typ=data.get('type')
            if typ=='join':
                name=(data.get('name') or (tg_user or {}).get('first_name') or 'Player').strip()[:32] or 'Player'
                p=_kingdom_find(room,session_id)
                if not p:
                    if room.get('ended'):
                        await ws.send_json({'type':'error','message':'This battle is already over.'}); continue
                    if room.get('started'):
                        await ws.send_json({'type':'error','message':'The battle has already started. Join the next room.'}); continue
                    if len(room['players'])>=6:
                        await ws.send_json({'type':'error','message':'Room is full (6 rulers max).'}); continue
                    p={'id':session_id,'name':name,'connected':True,'ws':ws,'kingdom':{
                        'gold':500,'food':220,'wood':180,'stone':140,'army':80,'population':120,
                        'level':1,'territory':25,'defense':30,'buildings':3,'wins':0,'losses':0}}
                    room['players'].append(p)
                else:
                    p['name']=name; p['connected']=True; p['ws']=ws
                room['updated']=time.time()
                started_now=_kingdom_start_if_ready(room)
                if started_now:
                    await broadcast_kingdom(
                        room,'event',
                        '⚔️ Two kingdoms have entered the war. The first turn begins now.',
                        {'kind':'battle_start'}
                    )
                else: await ws.send_str(json.dumps({'type':'joined','you':session_id,'state':kingdom_snapshot(room,session_id)},separators=(',',':')))
                if started_now: await ws.send_str(json.dumps({'type':'joined','you':session_id,'state':kingdom_snapshot(room,session_id)},separators=(',',':')))
            elif typ=='action':
                if room.get('ended'): continue
                p=_kingdom_find(room,session_id)
                if not p or not room.get('started'): continue

                action=(data.get('action') or '').lower()
                target=_kingdom_find(room,data.get('target'))
                before_actor=dict(p.get('kingdom') or {})
                before_target=dict(target.get('kingdom') or {}) if target else {}

                ok,message=_kingdom_action(room,p,action,data.get('target'))
                if not ok:
                    await ws.send_json({'type':'error','message':message}); continue

                if p['kingdom']['territory']>=70:
                    await _kingdom_end(room,p['id'],f"👑 {p['name']} reached 70 land and claimed the crown.")
                    continue

                after_actor=p.get('kingdom') or {}
                after_target=(target.get('kingdom') or {}) if target else {}
                meta={
                    'kind':'action',
                    'action':action,
                    'actorId':p['id'],
                    'actorName':p.get('name') or 'Ruler',
                    'targetId':target.get('id') if target else None,
                    'targetName':target.get('name') if target else None,
                    'armyBefore':int(before_actor.get('army',0)),
                    'armyAfter':int(after_actor.get('army',0)),
                    'territoryBefore':int(before_actor.get('territory',0)),
                    'territoryAfter':int(after_actor.get('territory',0)),
                    'targetTerritoryBefore':int(before_target.get('territory',0)) if target else None,
                    'targetTerritoryAfter':int(after_target.get('territory',0)) if target else None,
                    'targetArmyBefore':int(before_target.get('army',0)) if target else None,
                    'targetArmyAfter':int(after_target.get('army',0)) if target else None,
                    'success': 'captured' in str(message).lower(),
                }
                _kingdom_next(room)
                await broadcast_kingdom(room,'event',message,meta)
            elif typ=='leave':
                p=_kingdom_find(room,session_id)
                if p:
                    p['connected']=False
                    p['ws']=None
                    room['updated']=time.time()
                    await broadcast_kingdom(
                        room,'event',
                        f"👋 {p.get('name','Ruler')} left the war map.",
                        {'kind':'player_left','actorId':p.get('id'),'actorName':p.get('name','Ruler')}
                    )
    finally:
        p=_kingdom_find(room,session_id)
        if p and p.get('ws') is ws:
            p['connected']=False; p['ws']=None; room['updated']=time.time()
    return ws


# ---------------- CHESS MINI APP ----------------
CHESS_PIECES = {
    'P':'♙','N':'♘','B':'♗','R':'♖','Q':'♕','K':'♔',
    'p':'♟','n':'♞','b':'♝','r':'♜','q':'♛','k':'♚'
}

def new_chess_room():
    return {
        'code': None,
        'board': chesslib.Board() if chesslib else None,
        'players': [],
        'started': False,
        'winner': None,
        'draw': False,
        'payout_done': False,
        'reward_coins': 0,
        'reward_points': 0,
        'history': [],
        'last_move': None,
        'chat': [],
        'created': time.time(),
        'updated': time.time(),
        'ended': False,
    }

def create_chess_join_token(room_code, user_id, ttl=None):
    """Create a signed Chess room token bound to one Telegram user ID."""
    room_code = str(room_code or '').upper().strip()
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return ''
    ttl = int(ttl or os.getenv('CHESS_JOIN_TOKEN_TTL_SECONDS', '21600'))
    expires = int(time.time()) + max(300, ttl)
    secret = (os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN') or '').encode()
    if not secret or not room_code:
        return ''
    payload = f'{room_code}:{uid}:{expires}'
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f'{uid}.{expires}.{signature}'

def verify_chess_join_token(room_code, token):
    """Verify a signed Chess room token and return its Telegram user ID."""
    room_code = str(room_code or '').upper().strip()
    try:
        uid_s, exp_s, signature = str(token or '').split('.', 2)
        uid = int(uid_s)
        expires = int(exp_s)
    except (TypeError, ValueError):
        return None
    if not room_code or time.time() > expires:
        return None
    secret = (os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN') or '').encode()
    if not secret:
        return None
    payload = f'{room_code}:{uid}:{expires}'
    expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return uid if hmac.compare_digest(expected, signature) else None

async def create_chess_room_for_group(group_id=None):
    """Create a Chess room server-side so Telegram users can join securely."""
    if chesslib is None:
        return ''
    async with CHESS_LOCK:
        code = new_code()
        room = new_chess_room()
        room['code'] = code
        room['group_id'] = int(group_id) if group_id is not None else None
        CHESS_ROOMS[code] = room
        return code

def chess_player_public(p):
    return {
        'id':p['id'],
        'name':p['name'],
        'color':p['color'],
        'bot':p.get('bot',False),
        'connected':p.get('connected',False)
    }

def chess_state(room, you=None):
    b=room['board']
    pieces=[]
    if b:
        for sq in chesslib.SQUARES:
            p=b.piece_at(sq)
            if p:
                pieces.append({'square':chesslib.square_name(sq),'piece':CHESS_PIECES[p.symbol()]})
    turn='white' if b and b.turn else 'black'
    return {
        'type':'state',
        'room':room['code'],
        'started':room['started'],
        'ended':room.get('ended',False),
        'winner':room['winner'],
        'turn':turn,
        'fen':b.fen() if b else '',
        'pieces':pieces,
        'players':[chess_player_public(p) for p in room['players']],
        'you':you,
        'check':bool(b and b.is_check()),
        'checkmate':bool(b and b.is_checkmate()),
        'stalemate':bool(b and b.is_stalemate()),
        'draw':bool(room.get('draw') or (b and b.is_game_over() and not b.is_checkmate())),
        'history':room.get('history',[])[-80:],
        'last_move':room.get('last_move'),
        'legal_moves':([
            {'from':chesslib.square_name(m.from_square),'to':chesslib.square_name(m.to_square),'color':('white' if b.turn else 'black')}
            for m in list(b.legal_moves)
        ] if b else []),
        'reward_coins':int(room.get('reward_coins',0) or 0),
        'reward_points':int(room.get('reward_points',0) or 0),
        'chat':room['chat'][-30:]
    }

async def broadcast_chess(room):
    # A stale browser/deploy can leave a dead websocket object in the room.
    # Never let one failed send break the whole Chess connection loop.
    for p in list(room.get('players', [])):
        ws = p.get('ws')
        if not ws or ws.closed:
            continue
        try:
            await ws.send_json(chess_state(room, p['id']))
        except Exception as exc:
            p['connected'] = False
            p['ws'] = None
            print(f"[Chess][Broadcast] {type(exc).__name__}: {exc}")

def chess_current_player(room):
    if not room['board']:
        return None
    color='white' if room['board'].turn else 'black'
    return next((p for p in room['players'] if p['color']==color),None)

async def _chess_award(room):
    """Reward the Telegram winner exactly once, even after a transient DB error."""
    if not room.get('winner'):
        return
    winner_id = str(room.get('winner'))
    winner = next((p for p in room.get('players', []) if str(p.get('id')) == winner_id), None)
    if not winner:
        return
    try:
        numeric_uid = int(winner.get('id'))
    except (TypeError, ValueError):
        # Browser-only guests do not have a Telegram balance.
        return

    room_code = str(room.get('code') or 'unknown')
    reward_key = f"chess:{room_code}:{numeric_uid}"

    # Coin credit is guarded by a per-room marker on the user document.
    # A retry can therefore never pay the same Chess win twice.
    await ensure_user(type('ChessUser', (), {
        'id': numeric_uid,
        'first_name': winner.get('name') or 'Player',
        'username': None,
    })())
    try:
        coin_result = await users.update_one(
            {'_id': numeric_uid, 'chess_reward_rooms': {'$ne': room_code}},
            {
                '$inc': {'coins': 750},
                '$addToSet': {'chess_reward_rooms': room_code},
            },
        )
    except Exception as exc:
        print(f"[Chess][RewardCoins] {type(exc).__name__}: {exc}")
        return

    try:
        already_paid = coin_result.modified_count == 0
    except Exception:
        already_paid = False

    if not already_paid:
        try:
            await add_xp(numeric_uid, 100)
        except Exception as exc:
            print(f"[Chess][RewardXP] {type(exc).__name__}: {exc}")

    # Leaderboard entry is also idempotent by room + winner.
    # The write uses a deterministic _id, so retries cannot duplicate points.
    try:
        await game_stats.update_one(
            {'_id': reward_key},
            {
                '$setOnInsert': {
                    'uid': numeric_uid,
                    'game': 'CHESS',
                    'points': 750,
                    'wins': 1,
                    'chat_id': room.get('group_id'),
                    'created_at': datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        # Coins are already protected from double credit; a future call can retry
        # this leaderboard write safely using the same deterministic key.
        room['payout_done'] = False
        print(f"[Chess][RewardPoints] {type(exc).__name__}: {exc}")
        return

    room['payout_done'] = True
    room['reward_coins'] = 750
    room['reward_points'] = 750

async def create_chess_room(request):
    if chesslib is None: return web.json_response({'ok':False,'error':'Chess package unavailable'},status=500)
    async with CHESS_LOCK:
        code=new_code(); room=new_chess_room(); room['code']=code; room['group_id']=request_group_id(request); CHESS_ROOMS[code]=room
    return web.json_response({'ok':True,'room':code})

async def chess_claim(request):
    """Verify Telegram initData and mint a fresh signed Chess seat token."""
    code=request.match_info['code'].upper()
    room=CHESS_ROOMS.get(code)
    if not room:
        return web.json_response({'ok':False,'error':'Chess room expired. Open a fresh /chess room.'},status=404)

    tg_user=verify_telegram_init_data(request.query.get('initData',''))
    if not tg_user:
        return web.json_response({
            'ok':False,
            'error':'Telegram verification is unavailable. Re-open this Chess room from Vanya.'
        },status=401)

    uid=int(tg_user['id'])
    token=create_chess_join_token(code,uid)
    if not token:
        return web.json_response({'ok':False,'error':'Could not create a secure Chess seat.'},status=500)

    name=(tg_user.get('first_name') or request.query.get('name') or 'Player').strip()[:32] or 'Player'

    async with CHESS_LOCK:
        existing=next((p for p in room['players'] if str(p.get('id'))==str(uid)),None)
        if existing:
            existing['name']=name
            existing['telegram_id']=uid
            existing['connected']=True
        else:
            if len(room['players'])>=2:
                return web.json_response({
                    'ok':False,
                    'error':'Room is full. Only 2 Telegram players can join.'
                },status=409)
            color='white' if not any(p.get('color')=='white' for p in room['players']) else 'black'
            existing={
                'id':str(uid),
                'telegram_id':uid,
                'name':name,
                'color':color,
                'bot':False,
                'connected':True,
                'ws':None,
            }
            room['players'].append(existing)
        room['updated']=time.time()

    return web.json_response({
        'ok':True,
        'room':code,
        'token':token,
        'state':chess_state(room,str(uid)),
    })


async def chess_http_state(request):
    code=request.match_info['code'].upper()
    token=request.query.get('token','')
    init_data=request.query.get('initData','')
    token_uid=verify_chess_join_token(code,token)
    tg_user=verify_telegram_init_data(init_data)
    uid=token_uid if token_uid is not None else (tg_user.get('id') if tg_user else None)
    if uid is None:
        return web.json_response({'ok':False,'error':'Telegram verification required.'},status=401)
    room=CHESS_ROOMS.get(code)
    if not room:
        return web.json_response({'ok':False,'error':'Chess room expired. Open a fresh /chess room.'},status=404)
    if token_uid is not None and tg_user is not None and int(token_uid)!=int(tg_user.get('id')):
        return web.json_response({'ok':False,'error':'Telegram account verification mismatch.'},status=403)
    name=(request.query.get('name') or (tg_user or {}).get('first_name') or 'Player').strip()[:32] or 'Player'
    async with CHESS_LOCK:
        p=next((x for x in room['players'] if str(x.get('id'))==str(uid)),None)
        if not p:
            if len(room['players'])>=2:
                return web.json_response({'ok':False,'error':'Room is full. Only 2 players can join.'},status=409)
            color='white' if not any(x.get('color')=='white' for x in room['players']) else 'black'
            p={'id':str(uid),'telegram_id':int(uid),'name':name,'color':color,'bot':False,'connected':True,'ws':None}
            room['players'].append(p)
        else:
            p['name']=name
            p['connected']=True
        room['updated']=time.time()
    return web.json_response({'ok':True,'state':chess_state(room,str(uid))})

async def chess_http_action(request):
    code=request.match_info['code'].upper()
    token=request.query.get('token','')
    init_data=request.query.get('initData','')
    token_uid=verify_chess_join_token(code,token)
    tg_user=verify_telegram_init_data(init_data)
    uid=token_uid if token_uid is not None else (tg_user.get('id') if tg_user else None)
    if uid is None:
        return web.json_response({'ok':False,'error':'Telegram verification required.'},status=401)
    room=CHESS_ROOMS.get(code)
    if not room:
        return web.json_response({'ok':False,'error':'Chess room expired.'},status=404)
    if token_uid is not None and tg_user is not None and int(token_uid)!=int(tg_user.get('id')):
        return web.json_response({'ok':False,'error':'Telegram account verification mismatch.'},status=403)
    try: data=await request.json()
    except Exception: data={}
    typ=data.get('type')
    p=next((x for x in room['players'] if str(x.get('id'))==str(uid)),None)
    if typ=='add_bot':
        if room.get('started') or len(room['players'])>=2:
            return web.json_response({'ok':False,'error':'A bot cannot be added now.'},status=409)
        room['players'].append({'id':'bot-'+''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(8)),'name':'Bot Alpha','telegram_id':None,'color':'black','bot':True,'connected':True,'ws':None})
    elif typ=='start':
        if len(room['players'])<2:
            return web.json_response({'ok':False,'error':'2 players are needed, or add a bot.'},status=409)
        room['started']=True; room['draw']=False; room['winner']=None; room['payout_done']=False; room['reward_coins']=0; room['reward_points']=0; room['history']=[]; room['last_move']=None
    elif typ=='move':
        if not room.get('started') or room.get('winner') or room.get('draw'):
            return web.json_response({'ok':False,'error':'The game is not running.'},status=409)
        cur=chess_current_player(room)
        if not p or not cur or str(cur.get('id'))!=str(uid):
            return web.json_response({'ok':False,'error':'Not your turn.'},status=409)
        try: move=chesslib.Move.from_uci(data.get('uci',''))
        except Exception: return web.json_response({'ok':False,'error':'Invalid move.'},status=400)
        if move not in room['board'].legal_moves:
            return web.json_response({'ok':False,'error':'Illegal move.'},status=409)
        san=room['board'].san(move); room['board'].push(move); room['history'].append({'san':san,'color':'white' if p['color']=='white' else 'black'}); room['last_move']={'from':chesslib.square_name(move.from_square),'to':chesslib.square_name(move.to_square)}
        if room['board'].is_checkmate():
            room['winner']=str(uid); room['draw']=False; room['started']=False; await _chess_award(room)
        elif room['board'].is_game_over():
            room['draw']=True; room['started']=False
    elif typ=='resign':
        if p:
            opp=next((x for x in room['players'] if str(x.get('id'))!=str(uid)),None)
            room['winner']=opp['id'] if opp else None; room['draw']=False; room['started']=False
            if room.get('winner'): await _chess_award(room)
    elif typ=='chat':
        msgtext=(data.get('text') or '').strip()[:180]
        if p and msgtext:
            room['chat'].append({'name':p.get('name') or 'Player','text':msgtext})
    else:
        return web.json_response({'ok':False,'error':'Unknown Chess action.'},status=400)
    room['updated']=time.time()
    await broadcast_chess(room)
    if room.get('started') and not room.get('winner') and not room.get('draw'):
        nxt=chess_current_player(room)
        if nxt and nxt.get('bot'): asyncio.create_task(maybe_chess_bot_turn(room))
    return web.json_response({'ok':True,'state':chess_state(room,str(uid))})

async def chess_page(request):
    # Chess frontend changes must reach Telegram's in-app browser immediately.
    # Prevent stale cached HTML from keeping an older WebSocket client alive.
    response = web.FileResponse(WEB/'chess.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

async def maybe_chess_bot_turn(room):
    await asyncio.sleep(.65)
    if room.get('ended') or not room['started'] or room['winner'] or room.get('draw') or chesslib is None:
        return
    p=chess_current_player(room)
    if not p or not p.get('bot'):
        return
    moves=list(room['board'].legal_moves)
    if not moves:
        return
    captures=[m for m in moves if room['board'].is_capture(m)]
    move=random.choice(captures or moves)
    san=room['board'].san(move)
    room['board'].push(move)
    room['history'].append({'san':san,'color':'black'})
    room['last_move']={'from':chesslib.square_name(move.from_square),'to':chesslib.square_name(move.to_square)}
    room['updated']=time.time()
    if room['board'].is_checkmate():
        room['winner']=p['id']
        room['draw']=False
        room['started']=False
        await _chess_award(room)
    elif room['board'].is_game_over():
        room['draw']=True
        room['started']=False
    await broadcast_chess(room)

async def chess_ws(request):
    code=request.match_info['code'].upper()
    raw_token=request.query.get('token','')
    raw_init_data=request.query.get('initData','')
    print(f"[Chess][WS] connect code={code} token={'yes' if raw_token else 'no'} initData={'yes' if raw_init_data else 'no'}")
    ws=web.WebSocketResponse(heartbeat=25, max_msg_size=64 * 1024)
    try:
        await ws.prepare(request)
    except Exception as exc:
        print(f"[Chess][WS] handshake failed code={code}: {type(exc).__name__}: {exc}")
        raise

    tg_user=verify_telegram_init_data(raw_init_data)
    token_uid=verify_chess_join_token(code,raw_token)
    print(f"[Chess][WS] auth code={code} token_uid={'yes' if token_uid is not None else 'no'} tg_user={'yes' if tg_user else 'no'}")

    # Chess rooms are intentionally in-process for live play, so a Railway
    # deploy/restart can invalidate an older room URL. If the URL still carries
    # a valid signed creator token (or valid Telegram Mini App initData), safely
    # recreate that room under the same code instead of leaving the client in a
    # reconnect loop forever.
    room=CHESS_ROOMS.get(code)
    if not room and (token_uid is not None or tg_user is not None):
        async with CHESS_LOCK:
            room=CHESS_ROOMS.get(code)
            if not room:
                room=new_chess_room()
                room['code']=code
                room['group_id']=None
                CHESS_ROOMS[code]=room
                print(f"[Chess] Recovered stale room {code}")
    if not room:
        await ws.send_json({'type':'error','message':'This Chess room expired. Open a fresh Chess room from Vanya.'})
        await ws.close()
        return ws
    if token_uid is not None and tg_user is not None and int(tg_user.get('id')) != int(token_uid):
        await ws.send_json({'type':'error','message':'Telegram account verification mismatch.'})
        await ws.close()
        return ws

    verified_user_id = token_uid if token_uid is not None else (tg_user.get('id') if tg_user else None)

    # Chess is a Telegram-player game. A seat must map to exactly one Telegram
    # account; do not create anonymous browser seats that could bypass the
    # one-player-per-Telegram-ID rule.
    if verified_user_id is None:
        await ws.send_json({
            'type':'error',
            'message':'Open Chess from Vanya in Telegram. A Telegram account is required to join a seat.'
        })
        await ws.close()
        return ws

    session_id=str(verified_user_id)

    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT: continue
            try: data=json.loads(msg.data)
            except Exception: continue
            typ=data.get('type')
            if typ=='join':
                name=(data.get('name') or (tg_user or {}).get('first_name') or '').strip()[:32]
                if not name:
                    try:
                        existing=await users.find_one({'_id':int(verified_user_id)},{'name':1})
                        name=(existing or {}).get('name') or ''
                    except Exception:
                        pass
                name=name or 'Player'

                # One Telegram ID = one Chess seat in this room. Reconnecting
                # from the same account reuses that seat, but another seat can
                # never be created for the same Telegram user.
                duplicate=next(
                    (x for x in room['players']
                     if str(x.get('id')) == session_id),
                    None
                )
                p=duplicate

                if not p:
                    if len(room['players'])>=2:
                        await ws.send_json({'type':'error','message':'Room is full. Only 2 Telegram players can join.'})
                        continue
                    color='white' if not any(x['color']=='white' for x in room['players']) else 'black'
                    p={
                        'id':session_id,
                        'telegram_id':int(verified_user_id),
                        'name':name,
                        'color':color,
                        'bot':False,
                        'connected':True,
                        'ws':ws
                    }
                    room['players'].append(p)
                else:
                    # Existing Telegram seat: reconnect/update that seat instead
                    # of creating a second player.
                    p['name']=name
                    p['telegram_id']=int(verified_user_id)
                    p['connected']=True
                    p['ws']=ws

                room['updated']=time.time()
                await broadcast_chess(room)
            elif typ=='add_bot':
                if room['started'] or len(room['players'])>=2:
                    continue
                if not any(x.get('color')=='black' for x in room['players']):
                    bid='bot-'+''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(8))
                    room['players'].append({
                        'id':bid,
                        'name':'Bot Alpha',
                        'telegram_id':None,
                        'color':'black',
                        'bot':True,
                        'connected':True,
                        'ws':None
                    })
                    await broadcast_chess(room)
            elif typ=='start':
                if room.get('winner') or room.get('draw'):
                    await ws.send_json({'type':'error','message':'This chess room has finished. Create a new room.'})
                    continue
                if len(room['players'])<2:
                    await ws.send_json({'type':'error','message':'2 players are needed, or add a bot'})
                    continue
                room['started']=True
                room['draw']=False
                room['winner']=None
                room['payout_done']=False
                room['reward_coins']=0
                room['reward_points']=0
                room['history']=[]
                room['last_move']=None
                room['updated']=time.time()
                await broadcast_chess(room)
                if chess_current_player(room).get('bot'):
                    asyncio.create_task(maybe_chess_bot_turn(room))
            elif typ=='move':
                if not room['started'] or room['winner'] or room.get('draw'): continue
                p=next((x for x in room['players'] if x['id']==session_id),None); cur=chess_current_player(room)
                if not p or not cur or cur['id']!=session_id:
                    await ws.send_json({'type':'error','message':'Not your turn'})
                    continue
                try:
                    move=chesslib.Move.from_uci(data.get('uci',''))
                except Exception:
                    await ws.send_json({'type':'error','message':'Invalid move'})
                    continue
                if move not in room['board'].legal_moves:
                    await ws.send_json({'type':'error','message':'Illegal move'})
                    continue
                san=room['board'].san(move)
                room['board'].push(move)
                room['history'].append({'san':san,'color':'white' if p['color']=='white' else 'black'})
                room['last_move']={'from':chesslib.square_name(move.from_square),'to':chesslib.square_name(move.to_square)}
                room['updated']=time.time()
                if room['board'].is_checkmate():
                    room['winner']=session_id
                    room['draw']=False
                    room['started']=False
                    await _chess_award(room)
                elif room['board'].is_game_over():
                    room['draw']=True
                    room['started']=False
                await broadcast_chess(room)
                if room['started'] and not room['winner'] and not room.get('draw'):
                    nxt=chess_current_player(room)
                    if nxt and nxt.get('bot'):
                        asyncio.create_task(maybe_chess_bot_turn(room))
            elif typ=='resign':
                p=next((x for x in room['players'] if x['id']==session_id),None)
                if p:
                    opp=next((x for x in room['players'] if x['id']!=session_id),None)
                    room['winner']=opp['id'] if opp else None
                    room['draw']=False
                    room['started']=False
                    room['updated']=time.time()
                    if room.get('winner'):
                        await _chess_award(room)
                    await broadcast_chess(room)
            elif typ=='chat':
                p=next((x for x in room['players'] if x['id']==session_id),None); msgtext=(data.get('text') or '').strip()[:180]
                if p and msgtext:
                    room['chat'].append({'name':p['name'],'text':msgtext}); room['chat']=room['chat'][-30:]; await broadcast_chess(room)
    finally:
        p=next((x for x in room['players'] if x['id']==session_id),None)
        if p: p['connected']=False; p['ws']=None; room['updated']=time.time(); await broadcast_chess(room)
    return ws

# ---------------- SCRIBBLE MINI APP ----------------
def new_scribble_room():
    return {
        'code': None,
        'game': 'scribble',
        'players': [],
        'strokes': [],
        'chat': [],
        'created': time.time(),
        'updated': time.time(),
        'ended': False,
    }


def scribble_player_public(p):
    return {
        'id': p['id'],
        'name': p['name'],
        'connected': p.get('connected', False),
    }


def scribble_state(room):
    return {
        'type': 'state',
        'game': 'scribble',
        'room': room['code'],
        'players': [scribble_player_public(p) for p in room['players']],
        'strokes': room['strokes'][-4000:],
        'chat': room['chat'][-40:],
    }


async def broadcast_scribble(room, event=None):
    payload = scribble_state(room)
    if event:
        payload.update(event)
    msg = json.dumps(payload, separators=(',', ':'))
    dead = []
    for p in room['players']:
        ws = p.get('ws')
        if ws and not ws.closed:
            try:
                await ws.send_str(msg)
            except Exception:
                dead.append(p)
    for p in dead:
        p['ws'] = None
        p['connected'] = False


def scribble_find_player(room, pid):
    return next((x for x in room['players'] if x['id'] == pid), None)


async def create_scribble_room(request):
    async with ROOM_LOCK:
        code = new_code()
        room = new_scribble_room()
        room['code'] = code
        room['group_id'] = request_group_id(request)
        ROOMS['S:' + code] = room
    return web.json_response({'ok': True, 'room': code})


async def scribble_page(request):
    return web.FileResponse(WEB / 'scribble.html')


async def scribble_ws(request):
    code = request.match_info['code'].upper()
    room = ROOMS.get('S:' + code)
    if not room:
        return web.json_response({'ok': False, 'error': 'Room not found'}, status=404)

    ws = web.WebSocketResponse(heartbeat=25, max_msg_size=64 * 1024)
    await ws.prepare(request)

    tg_user = verify_telegram_init_data(request.query.get('initData', ''))
    client_id = ''.join(
        ch for ch in (request.query.get('cid') or '')
        if ch.isalnum() or ch in '_-'
    )[:80]
    session_id = str(tg_user['id']) if tg_user else (
        'guest-' + client_id if client_id
        else 'guest-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    )
    query_name = (request.query.get('name') or '').strip()[:32]

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except Exception:
                continue

            typ = data.get('type')

            if typ == 'join':
                name = (data.get('name') or query_name or (tg_user or {}).get('first_name') or 'Player').strip()[:32] or 'Player'
                p = scribble_find_player(room, session_id)
                if not p:
                    if len(room['players']) >= 12:
                        await ws.send_json({'type': 'error', 'message': 'Room is full'})
                        continue
                    p = {
                        'id': session_id,
                        'name': name,
                        'connected': True,
                        'ws': ws,
                    }
                    room['players'].append(p)
                else:
                    p['name'] = name
                    p['connected'] = True
                    p['ws'] = ws

                room['updated'] = time.time()
                await ws.send_str(json.dumps(scribble_state(room), separators=(',', ':')))
                await broadcast_scribble(room, {'event': 'joined', 'player': session_id})

            elif typ == 'stroke':
                p = scribble_find_player(room, session_id)
                stroke = data.get('stroke')
                if not p or not isinstance(stroke, dict):
                    continue
                a, b = stroke.get('a'), stroke.get('b')
                if not isinstance(a, dict) or not isinstance(b, dict):
                    continue
                try:
                    ax, ay = float(a.get('x')), float(a.get('y'))
                    bx, by = float(b.get('x')), float(b.get('y'))
                    size = max(1.0, min(40.0, float(stroke.get('size', 6))))
                except Exception:
                    continue
                color = str(stroke.get('color') or '#111111')[:20]
                clean = {
                    'a': {'x': max(0.0, min(1.0, ax)), 'y': max(0.0, min(1.0, ay))},
                    'b': {'x': max(0.0, min(1.0, bx)), 'y': max(0.0, min(1.0, by))},
                    'color': color,
                    'size': size,
                    'uid': session_id,
                }
                room['strokes'].append(clean)
                room['strokes'] = room['strokes'][-4000:]
                room['updated'] = time.time()
                await broadcast_scribble(room, {'event': 'stroke', 'stroke': clean})

            elif typ == 'undo':
                p = scribble_find_player(room, session_id)
                if not p:
                    continue
                index = next(
                    (i for i in range(len(room['strokes']) - 1, -1, -1)
                     if room['strokes'][i].get('uid') == session_id),
                    None
                )
                if index is None:
                    await ws.send_json({'type': 'error', 'message': 'Nothing from your drawing to undo'})
                    continue
                room['strokes'].pop(index)
                room['updated'] = time.time()
                await broadcast_scribble(room, {'event': 'undo'})

            elif typ == 'clear':
                if not scribble_find_player(room, session_id):
                    continue
                room['strokes'] = []
                room['updated'] = time.time()
                await broadcast_scribble(room, {'event': 'clear'})

            elif typ == 'chat':
                p = scribble_find_player(room, session_id)
                txt = str(data.get('text') or '').strip()[:180]
                if p and txt:
                    room['chat'].append({
                        'name': p['name'],
                        'text': txt,
                        'uid': session_id,
                    })
                    room['chat'] = room['chat'][-40:]
                    room['updated'] = time.time()
                    await broadcast_scribble(
                        room,
                        {'event': 'chat', 'name': p['name'], 'text': txt},
                    )
    finally:
        p = scribble_find_player(room, session_id)
        if p and p.get('ws') is ws:
            p['connected'] = False
            p['ws'] = None
            room['updated'] = time.time()
            await broadcast_scribble(room, {'event': 'left', 'player': session_id})

    return ws


# ---------------- UNO ----------------
UNO_COLORS=['red','green','blue','yellow']
UNO_COLOR_HEX={'red':'#ef625e','green':'#63c981','blue':'#63a4e2','yellow':'#f6bd35'}
UNO_WILD='wild'


def uno_card(color=None,value=None):
    if color is None:
        color=random.choice(UNO_COLORS)
    if value is None:
        value=random.choice([str(i) for i in range(10)]+['skip','reverse','+2'])
    return {'id':''.join(random.choice(string.ascii_letters+string.digits) for _ in range(10)),'color':color,'value':value}


def make_uno_deck():
    deck=[]
    for c in UNO_COLORS:
        deck.append(uno_card(c,'0'))
        for _ in range(2):
            for v in [str(i) for i in range(1,10)]+['skip','reverse','+2']:
                deck.append(uno_card(c,v))
    for _ in range(4):
        deck.append(uno_card(UNO_WILD,'wild')); deck.append(uno_card(UNO_WILD,'+4'))
    random.shuffle(deck); return deck


def new_uno_room():
    return {'code':None,'game':'uno','players':[],'started':False,'turn':0,'direction':1,'top':None,'deck':[],
            'discard':[],'winner':None,'pending_color':None,'payout_done':False,'chat':[],'created':time.time(),'updated':time.time(),'ended':False}


def uno_player_public(p):
    return {'id':p['id'],'name':p['name'],'color':p['color'],'bot':p['bot'],'connected':p['connected'],'count':len(p['hand'])}


def uno_state(room, you=None):
    cur=room['players'][room['turn']%len(room['players'])]['id'] if room['players'] else None
    top=room['top']
    me=uno_find(room,you) if you else None
    playable_ids=[]
    if me and cur==you and room.get('started') and not room.get('winner'):
        if room.get('drawn_card'):
            playable_ids=[c['id'] for c in me.get('hand',[]) if c.get('id')==room.get('drawn_card') and uno_can_play_card(room,me,c)]
        else:
            playable_ids=[c['id'] for c in me.get('hand',[]) if uno_can_play_card(room,me,c)]
    return {'type':'state','game':'uno','room':room['code'],'started':room['started'],'turn':cur,'direction':room['direction'],
            'winner':room['winner'],'top':top,'players':[uno_player_public(p) for p in room['players']],
            'you':you,'pending_color':room['pending_color'],'active_color':uno_active_color(room),
            'playable_ids':playable_ids,'drawn_card':room.get('drawn_card')}


async def _uno_award(room):
    """Reward Telegram players when an UNO match finishes."""
    if room.get('payout_done') or not room.get('winner'):
        return
    room['payout_done'] = True
    winner_id = str(room.get('winner'))
    for player in room.get('players', []):
        uid = player.get('id')
        try:
            numeric_uid = int(uid)
        except (TypeError, ValueError):
            continue
        try:
            won = str(uid) == winner_id
            if won:
                await add_coins(numeric_uid, 500)
                await add_xp(numeric_uid, 100)
                await record_game_result(numeric_uid, 'UNO', 500, True, room.get('group_id'))
            else:
                await add_coins(numeric_uid, 100)
                await add_xp(numeric_uid, 25)
                await record_game_result(numeric_uid, 'UNO', 100, False, room.get('group_id'))
        except Exception as exc:
            print(f"[UNO][Reward] {type(exc).__name__}: {exc}")


async def send_uno_state(room):
    dead=[]
    for p in room['players']:
        ws=p.get('ws')
        if ws and not ws.closed:
            payload=uno_state(room,p['id']); payload['hand']=p['hand']
            try: await ws.send_str(json.dumps(payload))
            except Exception: dead.append(p)
    for p in dead: p['ws']=None; p['connected']=False


def uno_current(room): return room['players'][room['turn']%len(room['players'])] if room['players'] else None

def uno_find(room,pid): return next((p for p in room['players'] if p['id']==pid),None)

def uno_active_color(room):
    top=room.get('top') or {}
    return room.get('pending_color') or top.get('color')

def uno_playable(card,top,pending_color):
    if not card or not top: return False
    if card.get('color')==UNO_WILD: return True
    target_color=pending_color or top.get('color')
    return card.get('color')==target_color or card.get('value')==top.get('value')

def uno_can_play_card(room,p,card):
    if not uno_playable(card,room.get('top'),room.get('pending_color')):
        return False
    if card.get('color')==UNO_WILD and card.get('value')=='+4':
        active=uno_active_color(room)
        if active and any(
            x.get('id')!=card.get('id') and x.get('color')==active
            for x in p.get('hand',[])
        ):
            return False
    return True


def uno_draw(room,n=1):
    for _ in range(n):
        if not room['deck']:
            keep=room['discard'][-1:] or []
            room['deck']=room['discard'][:-1]; room['discard']=keep; random.shuffle(room['deck'])
        if room['deck']:
            room['players'][room['turn']%len(room['players'])]['hand'].append(room['deck'].pop())


def uno_advance(room,steps=1): room['turn']=(room['turn']+room['direction']*steps)%len(room['players'])


def uno_apply_card(room,p,card):
    room['top']=card
    room['discard'].append(card)

    # A wild card keeps the chosen color active for the next player.
    # Normal cards clear any previous wild-color override.
    if card['color'] == UNO_WILD:
        if not room.get('pending_color'):
            room['pending_color'] = random.choice(UNO_COLORS)
    else:
        room['pending_color'] = None

    if card['value'] == '+2':
        # Draw two and skip the affected player's turn.
        uno_advance(room)
        uno_draw(room,2)
        uno_advance(room)
    elif card['value'] == 'skip':
        # With two players, skip must return the turn to the current player.
        # With 3+, move past exactly one player.
        uno_advance(room, 2)
    elif card['value'] == 'reverse':
        room['direction'] *= -1
        uno_advance(room)
    elif card['value'] == '+4':
        # Draw four and skip the affected player's turn.
        uno_advance(room)
        uno_draw(room,4)
        uno_advance(room)
    else:
        uno_advance(room)


async def maybe_uno_bot_turn(room):
    await asyncio.sleep(.9)
    if room.get('ended') or not room['started'] or room['winner']: return
    p=uno_current(room)
    if not p or not p.get('bot'): return
    playable=[c for c in p['hand'] if uno_can_play_card(room,p,c)]
    if playable:
        card=random.choice(playable); p['hand'].remove(card)
        if card['color']==UNO_WILD:
            room['pending_color']=random.choice(UNO_COLORS)
        uno_apply_card(room,p,card)
        event={'event':'play','player':p['id'],'card':card}
    else:
        before={c['id'] for c in p['hand']}
        uno_draw(room,1)
        drawn=next((c for c in p['hand'] if c['id'] not in before),None)
        if drawn and uno_can_play_card(room,p,drawn):
            p['hand'].remove(drawn)
            if drawn['color']==UNO_WILD:
                room['pending_color']=random.choice(UNO_COLORS)
            uno_apply_card(room,p,drawn)
            event={'event':'draw_play','player':p['id'],'card':drawn}
        else:
            uno_advance(room); event={'event':'draw','player':p['id']}
    if not p['hand']: room['winner']=p['id']
    if room.get('winner'): await _uno_award(room)
    room['updated']=time.time(); await send_uno_state(room)
    if room['started'] and not room['winner'] and uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))


async def create_uno_room(request):
    async with ROOM_LOCK:
        code=new_code(); room=new_uno_room(); room['code']=code; room['group_id']=request_group_id(request); room['deck']=make_uno_deck(); room['top']=room['deck'].pop();
        while room['top']['color']==UNO_WILD: room['deck'].insert(0,room['top']); room['top']=room['deck'].pop()
        room['discard']=[room['top']]; ROOMS['U:'+code]=room
    return web.json_response({'ok':True,'room':code})


async def uno_page(request): return web.FileResponse(WEB/'uno.html')


async def uno_ws(request):
    code=request.match_info['code'].upper(); room=ROOMS.get('U:'+code)
    if not room: return web.json_response({'ok':False,'error':'Room not found'},status=404)
    ws=web.WebSocketResponse(heartbeat=25); await ws.prepare(request)
    tg_user=verify_telegram_init_data(request.query.get('initData',''))
    session_id=str(tg_user['id']) if tg_user else 'guest-'+''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(12))
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT: continue
            try: data=json.loads(msg.data)
            except Exception: continue
            typ=data.get('type')
            if typ=='join':
                name=(data.get('name') or (tg_user or {}).get('first_name') or 'Player')[:32]
                p=uno_find(room,session_id)
                if not p:
                    if len(room['players'])>=4: await ws.send_json({'type':'error','message':'Room is full'}); continue
                    color=UNO_COLORS[len(room['players'])]
                    p={'id':session_id,'name':name,'color':color,'bot':False,'connected':True,'ws':ws,'hand':[]}
                    room['players'].append(p)
                    for _ in range(7): p['hand'].append(room['deck'].pop())
                else: p['name']=name; p['connected']=True; p['ws']=ws
                room['updated']=time.time(); await send_uno_state(room)
            elif typ=='add_bot':
                if room['started'] or len(room['players'])>=4: continue
                color=UNO_COLORS[len(room['players'])]; bid='bot-'+''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(8))
                p={'id':bid,'name':'Bot '+str(sum(1 for x in room['players'] if x.get('bot'))+1),'color':color,'bot':True,'connected':True,'ws':None,'hand':[room['deck'].pop() for _ in range(7)]}
                room['players'].append(p); room['updated']=time.time(); await send_uno_state(room)
            elif typ=='start':
                if len(room['players'])<2: await ws.send_json({'type':'error','message':'At least 2 players are needed'}); continue
                room['started']=True; room['winner']=None; room['payout_done']=False; room['turn']=0; room['direction']=1; room['pending_color']=None; room['drawn_card']=None; room['updated']=time.time(); await send_uno_state(room)
                if uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))
            elif typ=='draw':
                if not room['started'] or room['winner']: continue
                p=uno_find(room,session_id); cur=uno_current(room)
                if not p or not cur or cur['id']!=session_id:
                    await ws.send_json({'type':'error','message':'Wait for your turn'})
                    continue
                if room.get('drawn_card'):
                    await ws.send_json({'type':'error','message':'Play or pass the card you just drew'})
                    continue
                before={card['id'] for card in p['hand']}
                uno_draw(room,1)
                drawn=next((card for card in p['hand'] if card['id'] not in before),None)
                if drawn and uno_playable(drawn,room['top'],room['pending_color']):
                    room['drawn_card']=drawn['id']
                else:
                    room['drawn_card']=None
                    uno_advance(room)
                room['updated']=time.time(); await send_uno_state(room)
                if not room.get('drawn_card') and uno_current(room).get('bot'):
                    asyncio.create_task(maybe_uno_bot_turn(room))
            elif typ=='play':
                if not room['started'] or room['winner']: continue
                p=uno_find(room,session_id); cur=uno_current(room)
                if not p or not cur or cur['id']!=session_id: await ws.send_json({'type':'error','message':'Wait for your turn'}); continue
                cid=data.get('card_id'); card=next((c for c in p['hand'] if c['id']==cid),None)
                if not card:
                    await ws.send_json({'type':'error','message':'Card not found'})
                    continue
                if room.get('drawn_card') and cid != room['drawn_card']:
                    await ws.send_json({'type':'error','message':'You can only play the card you just drew'})
                    continue
                if not uno_can_play_card(room,p,card):
                    if card.get('color')==UNO_WILD and card.get('value')=='+4':
                        await ws.send_json({'type':'error','message':'+4 is blocked because you have a card matching the active color'})
                    else:
                        await ws.send_json({'type':'error','message':'That card cannot be played on the current card'})
                    continue
                if card['color']==UNO_WILD:
                    chosen=data.get('color')
                    if chosen not in UNO_COLORS:
                        await ws.send_json({'type':'error','message':'Choose a color for the Wild card'})
                        continue
                p['hand'].remove(card)
                room['drawn_card']=None
                if card['color']==UNO_WILD:
                    room['pending_color']=chosen
                uno_apply_card(room,p,card)
                if not p['hand']: room['winner']=p['id']
                if room.get('winner'): await _uno_award(room)
                room['updated']=time.time(); await send_uno_state(room)
                if room['started'] and not room['winner'] and uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))
    finally:
        p=uno_find(room,session_id)
        if p:
            p['connected']=False
            p['ws']=None
            room['updated']=time.time()
        try:
            await send_uno_state(room)
        except Exception:
            pass
    return ws

async def world_identity(request):
    tg_user = verify_telegram_init_data(request.query.get('initData', ''))
    if tg_user:
        class U: pass
        u = U(); u.id = tg_user['id']; u.first_name = tg_user.get('first_name') or 'Player'; u.username = tg_user.get('username')
        try: await ensure_user(u)
        except Exception: pass
        return ('user', tg_user['id'])
    cid = ''.join(ch for ch in (request.query.get('cid') or '') if ch.isalnum() or ch in '_-')[:80]
    if not cid: cid = 'guest-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(16))
    return ('guest', cid)

async def world_load(request):
    kind, ident = await world_identity(request)
    if kind == 'user':
        u = await users.find_one({'_id': ident}, {'world':1,'coins':1,'xp':1,'level':1,'name':1}) or {}
        world = normalize_world(u.get('world'))
        await users.update_one({'_id': ident}, {'$set': {'world': world}}, upsert=True)
        return ident, world, int(u.get('coins',0)), int(u.get('xp',0)), int(u.get('level',1)), u.get('name') or 'Player'
    world = normalize_world(WORLD_GUESTS.get(ident)); WORLD_GUESTS[ident] = world
    return ident, world, 1000, 0, 1, 'Guest Player'

def world_payload(world, coins, xp, level, name):
    return {'ok': True, 'name': name, 'coins': coins, 'xp': xp, 'level': level, 'city': world['city'], 'room': world['room'], 'pet': world['pet']}

async def world_state(request):
    _, world, coins, xp, level, name = await world_load(request)
    return web.json_response(world_payload(world, coins, xp, level, name))

async def world_action(request):
    try: data = await request.json()
    except Exception: data = {}
    action = (data.get('action') or '').strip()
    kind, ident = await world_identity(request)
    _, world, coins, xp, level, name = await world_load(request)
    now = int(time.time()); city, room, pet = world['city'], world['room'], world['pet']; message='Done ✨'
    if action == 'collect':
        if now - int(city.get('last_collect') or 0) < 3600: return web.json_response({'ok':False,'message':'✨ City drop already collected. Come back later.'})
        coins += 50; city['last_collect']=now; message='✨ You collected 50 coins from Vanya City!'
    elif action == 'daily':
        if now - int(city.get('last_drop') or 0) < 86400: return web.json_response({'ok':False,'message':'🎁 Today’s City Drop is already claimed.'})
        coins += 150; city['last_drop']=now; message='🎁 City Drop claimed! +150 🪙'
    elif action == 'upgrade':
        building=data.get('building')
        if building not in ('arcade','cafe','market'): return web.json_response({'ok':False,'message':'Unknown building.'})
        cur=int(city['buildings'].get(building,1)); base={'arcade':250,'cafe':200,'market':300}[building]; cost=int(round(base*(1.45**(cur-1))))
        if coins<cost: return web.json_response({'ok':False,'message':f'Need {cost} 🪙 for the next upgrade.'})
        coins-=cost; city['buildings'][building]=cur+1; city['level']=1+sum(int(v)-1 for v in city['buildings'].values())//3; xp+=60; level=1+xp//1000; message=f'🏗️ {building.title()} upgraded to Lv.{cur+1}!'
    elif action == 'theme':
        themes={'neon':'Neon','sunset':'Sunset','mint':'Mint'}; key=str(data.get('theme') or '').lower()
        if key not in themes: return web.json_response({'ok':False,'message':'Theme unavailable.'})
        room['theme']=themes[key]; message=f'🎨 Room theme changed to {themes[key]}!'
    elif action == 'buy':
        item=str(data.get('item') or ''); prices={'lamp':300,'console':450,'bed':600}
        if item not in prices: return web.json_response({'ok':False,'message':'Item unavailable.'})
        if item in room['items']: return web.json_response({'ok':False,'message':'You already own that item.'})
        if coins<prices[item]: return web.json_response({'ok':False,'message':f'Need {prices[item]} 🪙.'})
        coins-=prices[item]; room['items'].append(item); message=f'🛋️ Unlocked {item.title()} for your room!'
    elif action == 'pet_feed':
        if coins<20: return web.json_response({'ok':False,'message':'Need 20 🪙 to feed Mochi.'})
        coins-=20; pet['hunger']=min(100,pet['hunger']+20); pet['happiness']=min(100,pet['happiness']+8); pet['xp']+=12; message='🍖 Mochi loved the snack!'
    elif action == 'pet_play':
        if pet['energy']<12: return web.json_response({'ok':False,'message':'⚡ Mochi is tired. Let the pet sleep first.'})
        pet['energy']=max(0,pet['energy']-12); pet['happiness']=min(100,pet['happiness']+18); pet['hunger']=max(0,pet['hunger']-5); pet['xp']+=22; coins+=10; message='🎾 Mochi had fun! +10 🪙'
    elif action == 'pet_sleep':
        pet['energy']=min(100,pet['energy']+30); pet['happiness']=min(100,pet['happiness']+4); pet['xp']+=6; message='🌙 Mochi took a cozy nap.'
    elif action == 'rename':
        new_name=str(data.get('name') or '').strip()[:18]
        if not new_name: return web.json_response({'ok':False,'message':'Enter a valid pet name.'})
        pet['name']=new_name; message=f'✨ Your pet is now called {new_name}!'
    else:
        return web.json_response({'ok':False,'message':'Unknown action.'})
    pet['level']=1+pet['xp']//100; pet['last_tick']=now
    if kind=='user':
        await users.update_one({'_id':ident},{'$set':{'world':world,'coins':coins,'xp':xp,'level':level}},upsert=True)
    else: WORLD_GUESTS[ident]=world
    return web.json_response({'ok':True,'message':message,'state':world_payload(world,coins,xp,level,name)})


async def config(request):
    return web.json_response({'bot_username':os.getenv('BOT_USERNAME','ItzVanyaBot').lstrip('@')})


async def health(request): return web.json_response({'ok':True,'app':'ItzVanyaBot Games Web Apps','ludo_rooms':sum(1 for k in ROOMS if k.startswith('L:')),'uno_rooms':sum(1 for k in ROOMS if k.startswith('U:')),'kingdom_rooms':len(KINGDOM_ROOMS)})


async def end_web_rooms_for_group(group_id):
    """End every active browser game room launched from this Telegram group.

    /end lives only in the Telegram group. The web apps do not need their own
    /end command; they receive a server-side game_ended event and close.
    """
    ended = 0
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return 0

    payload = json.dumps({
        'type': 'game_ended',
        'message': 'This game was ended from the Telegram group by /end.',
    }, separators=(',', ':'))

    async def stop_room(room):
        # Mark ended first so delayed bot turns cannot keep the match alive.
        room['ended'] = True
        room['started'] = False
        room['winner'] = None

        sockets = []
        for player in room.get('players', []):
            ws = player.get('ws')
            if ws and not ws.closed:
                sockets.append(ws)

        # Ludo can have spectators connected outside the player seats.
        for ws in room.get('spectators', []):
            if ws and not ws.closed:
                sockets.append(ws)

        seen = set()
        for ws in sockets:
            marker = id(ws)
            if marker in seen:
                continue
            seen.add(marker)
            try:
                await ws.send_str(payload)
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass

        room['spectators'] = []

    for key, room in list(ROOMS.items()):
        if room.get('group_id') != gid:
            continue
        await stop_room(room)
        ROOMS.pop(key, None)
        ended += 1

    for code, room in list(CHESS_ROOMS.items()):
        if room.get('group_id') != gid:
            continue
        await stop_room(room)
        CHESS_ROOMS.pop(code, None)
        ended += 1

    return ended

async def cleanup_rooms(app):
    while True:
        await asyncio.sleep(300); now=time.time()
        for code,room in list(ROOMS.items()):
            if now-room['updated']>21600: ROOMS.pop(code,None)
        for code,room in list(CHESS_ROOMS.items()):
            if now-room['updated']>21600: CHESS_ROOMS.pop(code,None)
        for code,room in list(KINGDOM_ROOMS.items()):
            if now-room['updated']>21600:
                task=room.get('timer_task')
                if task and not task.done(): task.cancel()
                KINGDOM_ROOMS.pop(code,None)


async def cleanup_ctx(app):
    task=asyncio.create_task(cleanup_rooms(app))
    try: yield
    finally: task.cancel()


async def start_web_server():
    app=web.Application()
    app.router.add_get('/',health); app.router.add_get('/health',health); app.router.add_get('/api/config',config)
    app.router.add_post('/api/rooms',create_ludo_room); app.router.add_post('/api/uno/rooms',create_uno_room); app.router.add_post('/api/chess/rooms',create_chess_room); app.router.add_post('/api/scribble/rooms',create_scribble_room); app.router.add_post('/api/kingdom/rooms',create_kingdom_room)
    app.router.add_get('/ludo',ludo_page); app.router.add_get('/ws/ludo/{code}',ludo_ws); app.router.add_get('/scribble',scribble_page); app.router.add_get('/ws/scribble/{code}',scribble_ws)
    app.router.add_get('/uno',uno_page); app.router.add_get('/ws/uno/{code}',uno_ws); app.router.add_get('/chess',chess_page); app.router.add_get('/chess-live',chess_page); app.router.add_get('/api/chess/claim/{code}',chess_claim); app.router.add_get('/api/chess/state/{code}',chess_http_state); app.router.add_post('/api/chess/action/{code}',chess_http_action); app.router.add_get('/ws/chess/{code}',chess_ws); app.router.add_get('/kingdom-wars',kingdom_page); app.router.add_get('/ws/kingdom/{code}',kingdom_ws )
    # Vanya World aliases all point to the same 3D page; query ?tab= selects City/Room/Pet.
    world_page = lambda request: web.FileResponse(WEB/'vanya_world.html')
    app.router.add_get('/vanya-city', world_page); app.router.add_get('/world', world_page); app.router.add_get('/vanya-world', world_page)
    app.router.add_get('/city', world_page); app.router.add_get('/room', world_page); app.router.add_get('/pet', world_page)
    app.router.add_get('/api/world/state',world_state); app.router.add_post('/api/world/action',world_action)
    app.router.add_static('/ludo/',WEB,show_index=False); app.router.add_static('/uno/',WEB,show_index=False); app.router.add_static('/chess/',WEB,show_index=False); app.router.add_static('/scribble/',WEB,show_index=False); app.router.add_static('/kingdom-wars/',WEB,show_index=False)
    app.cleanup_ctx.append(cleanup_ctx)
    runner=web.AppRunner(app); await runner.setup(); port=int(os.getenv('PORT','8080')); await web.TCPSite(runner,'0.0.0.0',port).start(); return runner
