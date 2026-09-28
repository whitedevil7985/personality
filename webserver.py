import os
import json
import random
import string
import asyncio
import hashlib
import hmac
import time
from pathlib import Path
from aiohttp import web, WSMsgType
from db import users, ensure_user
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
COLORS = ['red', 'green', 'yellow', 'blue']
COLOR_NAMES = {'red':'RED','green':'GREEN','yellow':'YELLOW','blue':'BLUE'}


def new_code():
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(random.choice(alphabet) for _ in range(6))
        if code not in ROOMS:
            return code


def new_room(game='ludo'):
    return {
        'code': None, 'game': game, 'players': [], 'started': False, 'turn': 0,
        'positions': {}, 'winner': None, 'last_roll': 0, 'created': time.time(),
        'updated': time.time(), 'chat': [], 'pending_roll': 0, 'movable': [], 'spectators': []
    }


def verify_telegram_init_data(init_data: str):
    if not init_data:
        return None
    try:
        pairs = [p.split('=', 1) for p in init_data.split('&') if '=' in p]
        data = {k: v for k, v in pairs}
        received = data.pop('hash', '')
        if not received:
            return None
        bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN') or ''
        if not bot_token:
            return None
        check = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
        secret = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
        digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, received):
            return None
        auth_date = int(data.get('auth_date', '0'))
        if auth_date and time.time() - auth_date > 86400:
            return None
        import urllib.parse
        user = json.loads(urllib.parse.unquote(data.get('user', '{}')))
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


# Standard 15x15 Ludo path. progress -1 means home, 0..51 means outer
# track, 52..55 means the five coloured home-lane squares, and 56 means
# the centre finish.
LUDO_PATH_LEN = 52
LUDO_PATH = [
    (6,0),(6,1),(6,2),(6,3),(6,4),(6,5),(5,6),(4,6),(3,6),(2,6),(1,6),(0,6),
    (0,7),(0,8),(1,8),(2,8),(3,8),(4,8),(5,8),(6,9),(6,10),(6,11),(6,12),(6,13),(6,14),
    (7,14),(8,14),(8,13),(8,12),(8,11),(8,10),(8,9),(9,8),(10,8),(11,8),(12,8),(13,8),(14,8),
    (14,7),(14,6),(13,6),(12,6),(11,6),(10,6),(9,6),(8,5),(8,4),(8,3),(8,2),(8,1),(8,0),(7,0)
]
LUDO_START = {'green': 1, 'yellow': 14, 'blue': 27, 'red': 40}
LUDO_LANES = {
    'green': [(7,1),(7,2),(7,3),(7,4),(7,5)],
    'yellow': [(1,7),(2,7),(3,7),(4,7),(5,7)],
    'blue': [(7,13),(7,12),(7,11),(7,10),(7,9)],
    'red': [(13,7),(12,7),(11,7),(10,7),(9,7)],
}
# Standard-looking safe squares plus each colour's starting square.
LUDO_SAFE = {1, 9, 14, 22, 27, 35, 40, 48}
LUDO_FINISH = 56
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


def ludo_reset_roll(room):
    room['pending_roll'] = 0
    room['movable'] = []


async def maybe_ludo_bot_turn(room):
    # One task per room keeps rapid state updates from spawning duplicate bot turns.
    await asyncio.sleep(0.65)
    if not room['started'] or room['winner'] or room.get('pending_roll'):
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
    if not room['winner'] and roll != 6:
        ludo_advance_turn(room)
    room['updated'] = time.time()
    await broadcast_ludo(room, {
        'event': 'move', 'player': p['id'], 'token': token, 'newpos': newpos,
        'captured': captured, 'roll': roll,
    })
    if room['started'] and not room['winner'] and current_player(room) and current_player(room).get('bot'):
        asyncio.create_task(maybe_ludo_bot_turn(room))


async def create_ludo_room(request):
    async with ROOM_LOCK:
        code = new_code()
        room = new_room('ludo')
        room['code'] = code
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
                if not room['winner'] and roll != 6:
                    ludo_advance_turn(room)
                room['updated'] = time.time()
                await broadcast_ludo(room, {
                    'event': 'move', 'player': p['id'], 'token': token, 'newpos': newpos,
                    'captured': captured, 'roll': roll,
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


# ---------------- CHESS MINI APP ----------------
CHESS_PIECES = {
    'P':'♙','N':'♘','B':'♗','R':'♖','Q':'♕','K':'♔',
    'p':'♟','n':'♞','b':'♝','r':'♜','q':'♛','k':'♚'
}

def new_chess_room():
    return {'code':None,'board':chesslib.Board() if chesslib else None,'players':[],
            'started':False,'winner':None,'chat':[],'created':time.time(),'updated':time.time()}

def chess_player_public(p):
    return {'id':p['id'],'name':p['name'],'color':p['color'],'bot':p.get('bot',False),'connected':p.get('connected',False)}

def chess_state(room, you=None):
    b=room['board']
    pieces=[]
    if b:
        for sq in chesslib.SQUARES:
            p=b.piece_at(sq)
            if p: pieces.append({'square':chesslib.square_name(sq),'piece':CHESS_PIECES[p.symbol()]})
    turn='white' if b and b.turn else 'black'
    return {'type':'state','room':room['code'],'started':room['started'],'winner':room['winner'],
            'turn':turn,'fen':b.fen() if b else '', 'pieces':pieces,
            'players':[chess_player_public(p) for p in room['players']], 'you':you,
            'check':bool(b and b.is_check()), 'checkmate':bool(b and b.is_checkmate()),
            'stalemate':bool(b and b.is_stalemate()), 'draw':bool(b and b.is_insufficient_material()),
            'chat':room['chat'][-30:]}

async def broadcast_chess(room):
    for p in room['players']:
        if p.get('ws') and not p['ws'].closed:
            await p['ws'].send_json(chess_state(room,p['id']))

def chess_current_player(room):
    if not room['board']: return None
    color='white' if room['board'].turn else 'black'
    return next((p for p in room['players'] if p['color']==color),None)

async def create_chess_room(request):
    if chesslib is None: return web.json_response({'ok':False,'error':'Chess package unavailable'},status=500)
    async with CHESS_LOCK:
        code=new_code(); room=new_chess_room(); room['code']=code; CHESS_ROOMS[code]=room
    return web.json_response({'ok':True,'room':code})

async def chess_page(request): return web.FileResponse(WEB/'chess.html')

async def maybe_chess_bot_turn(room):
    await asyncio.sleep(.65)
    if not room['started'] or room['winner'] or chesslib is None: return
    p=chess_current_player(room)
    if not p or not p.get('bot'): return
    moves=list(room['board'].legal_moves)
    if not moves: return
    # prefer captures/checks when available, otherwise random legal move
    captures=[m for m in moves if room['board'].is_capture(m)]
    move=random.choice(captures or moves)
    room['board'].push(move); room['updated']=time.time()
    if room['board'].is_checkmate(): room['winner']=p['id']
    await broadcast_chess(room)

async def chess_ws(request):
    code=request.match_info['code'].upper(); room=CHESS_ROOMS.get(code)
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
                p=next((x for x in room['players'] if x['id']==session_id),None)
                if not p:
                    if len(room['players'])>=2: await ws.send_json({'type':'error','message':'Room is full'}); continue
                    color='white' if not any(x['color']=='white' for x in room['players']) else 'black'
                    p={'id':session_id,'name':name,'color':color,'bot':False,'connected':True,'ws':ws}
                    room['players'].append(p)
                else: p['name']=name; p['connected']=True; p['ws']=ws
                room['updated']=time.time(); await broadcast_chess(room)
            elif typ=='add_bot':
                if room['started'] or len(room['players'])>=2: continue
                if not any(x.get('color')=='black' for x in room['players']):
                    bid='bot-'+''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(8))
                    room['players'].append({'id':bid,'name':'Bot Alpha','color':'black','bot':True,'connected':True,'ws':None})
                    await broadcast_chess(room)
            elif typ=='start':
                if len(room['players'])<2: await ws.send_json({'type':'error','message':'2 players are needed, or add a bot'}); continue
                room['started']=True; room['updated']=time.time(); await broadcast_chess(room)
                if chess_current_player(room).get('bot'): asyncio.create_task(maybe_chess_bot_turn(room))
            elif typ=='move':
                if not room['started'] or room['winner']: continue
                p=next((x for x in room['players'] if x['id']==session_id),None); cur=chess_current_player(room)
                if not p or not cur or cur['id']!=session_id: await ws.send_json({'type':'error','message':'Not your turn'}); continue
                try: move=chesslib.Move.from_uci(data.get('uci',''))
                except Exception: await ws.send_json({'type':'error','message':'Invalid move'}); continue
                if move not in room['board'].legal_moves: await ws.send_json({'type':'error','message':'Illegal move'}); continue
                room['board'].push(move); room['updated']=time.time()
                if room['board'].is_checkmate(): room['winner']=session_id
                await broadcast_chess(room)
                if room['started'] and not room['winner'] and chess_current_player(room).get('bot'): asyncio.create_task(maybe_chess_bot_turn(room))
            elif typ=='resign':
                p=next((x for x in room['players'] if x['id']==session_id),None)
                if p:
                    opp=next((x for x in room['players'] if x['id']!=session_id),None); room['winner']=opp['id'] if opp else None; room['started']=False; await broadcast_chess(room)
            elif typ=='chat':
                p=next((x for x in room['players'] if x['id']==session_id),None); msgtext=(data.get('text') or '').strip()[:180]
                if p and msgtext:
                    room['chat'].append({'name':p['name'],'text':msgtext}); room['chat']=room['chat'][-30:]; await broadcast_chess(room)
    finally:
        p=next((x for x in room['players'] if x['id']==session_id),None)
        if p: p['connected']=False; p['ws']=None; room['updated']=time.time(); await broadcast_chess(room)
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
            'discard':[],'winner':None,'pending_color':None,'chat':[],'created':time.time(),'updated':time.time()}


def uno_player_public(p):
    return {'id':p['id'],'name':p['name'],'color':p['color'],'bot':p['bot'],'connected':p['connected'],'count':len(p['hand'])}


def uno_state(room, you=None):
    cur=room['players'][room['turn']%len(room['players'])]['id'] if room['players'] else None
    top=room['top']
    return {'type':'state','game':'uno','room':room['code'],'started':room['started'],'turn':cur,'direction':room['direction'],
            'winner':room['winner'],'top':top,'players':[uno_player_public(p) for p in room['players']],
            'you':you,'pending_color':room['pending_color']}


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

def uno_playable(card,top,pending_color):
    if card['color']==UNO_WILD: return True
    target_color=pending_color or top['color']
    return card['color']==target_color or card['value']==top['value']


def uno_draw(room,n=1):
    for _ in range(n):
        if not room['deck']:
            keep=room['discard'][-1:] or []
            room['deck']=room['discard'][:-1]; room['discard']=keep; random.shuffle(room['deck'])
        if room['deck']:
            room['players'][room['turn']%len(room['players'])]['hand'].append(room['deck'].pop())


def uno_advance(room,steps=1): room['turn']=(room['turn']+room['direction']*steps)%len(room['players'])


def uno_apply_card(room,p,card):
    room['top']=card; room['discard'].append(card); room['pending_color']=None
    if card['value']=='+2': uno_advance(room); uno_draw(room,2)
    elif card['value']=='skip': uno_advance(room,2)
    elif card['value']=='reverse':
        room['direction']*=-1; uno_advance(room)
    elif card['value']=='+4': uno_advance(room); uno_draw(room,4)
    else: uno_advance(room)


async def maybe_uno_bot_turn(room):
    await asyncio.sleep(.9)
    if not room['started'] or room['winner']: return
    p=uno_current(room)
    if not p or not p.get('bot'): return
    playable=[c for c in p['hand'] if uno_playable(c,room['top'],room['pending_color'])]
    if playable:
        card=random.choice(playable); p['hand'].remove(card)
        if card['color']==UNO_WILD:
            room['pending_color']=random.choice(UNO_COLORS)
        uno_apply_card(room,p,card)
        event={'event':'play','player':p['id'],'card':card}
    else:
        uno_draw(room,1); uno_advance(room); event={'event':'draw','player':p['id']}
    if not p['hand']: room['winner']=p['id']
    room['updated']=time.time(); await send_uno_state(room)
    if room['started'] and not room['winner'] and uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))


async def create_uno_room(request):
    async with ROOM_LOCK:
        code=new_code(); room=new_uno_room(); room['code']=code; room['deck']=make_uno_deck(); room['top']=room['deck'].pop();
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
                room['started']=True; room['winner']=None; room['turn']=0; room['updated']=time.time(); await send_uno_state(room)
                if uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))
            elif typ=='draw':
                if not room['started'] or room['winner']: continue
                p=uno_find(room,session_id); cur=uno_current(room)
                if not p or not cur or cur['id']!=session_id: await ws.send_json({'type':'error','message':'Wait for your turn'}); continue
                uno_draw(room,1); uno_advance(room); room['updated']=time.time(); await send_uno_state(room)
                if uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))
            elif typ=='play':
                if not room['started'] or room['winner']: continue
                p=uno_find(room,session_id); cur=uno_current(room)
                if not p or not cur or cur['id']!=session_id: await ws.send_json({'type':'error','message':'Wait for your turn'}); continue
                cid=data.get('card_id'); card=next((c for c in p['hand'] if c['id']==cid),None)
                if not card: continue
                if not uno_playable(card,room['top'],room['pending_color']): await ws.send_json({'type':'error','message':'Play a matching card'}); continue
                p['hand'].remove(card)
                if card['color']==UNO_WILD:
                    chosen=data.get('color') if data.get('color') in UNO_COLORS else 'red'
                    room['pending_color']=chosen
                uno_apply_card(room,p,card)
                if not p['hand']: room['winner']=p['id']
                room['updated']=time.time(); await send_uno_state(room)
                if room['started'] and not room['winner'] and uno_current(room).get('bot'): asyncio.create_task(maybe_uno_bot_turn(room))
            elif typ=='chat':
                p=uno_find(room,session_id); text=(data.get('text') or '').strip()[:180]
                if p and text:
                    room['chat'].append({'name':p['name'],'text':text}); room['chat']=room['chat'][-30:]
                    for x in room['players']:
                        if x.get('ws') and not x['ws'].closed:
                            await x['ws'].send_json({'type':'chat','name':p['name'],'text':text})
    finally:
        p=uno_find(room,session_id)
        if p: p['connected']=False; p['ws']=None; room['updated']=time.time(); await send_uno_state(room)
    return ws


# ---------------- VANYA WORLD: CITY + ROOM + PET ----------------
WORLD_GUESTS = {}
WORLD_DEFAULT = {
    'city': {'level': 1, 'buildings': {'arcade': 1, 'cafe': 1, 'market': 1}, 'last_drop': 0, 'last_collect': 0},
    'room': {'theme': 'Neon', 'items': ['base-couch', 'base-plant', 'base-trophy']},
    'pet': {'name': 'Mochi', 'species': 'fox', 'hunger': 80, 'happiness': 80, 'energy': 80, 'xp': 0, 'level': 1, 'last_tick': 0},
}

def world_defaults():
    import copy
    return copy.deepcopy(WORLD_DEFAULT)

def normalize_world(w):
    base = world_defaults()
    if isinstance(w, dict):
        for section in ('city', 'room', 'pet'):
            if isinstance(w.get(section), dict):
                base[section].update(w[section])
    base['city']['buildings'] = {**WORLD_DEFAULT['city']['buildings'], **(base['city'].get('buildings') or {})}
    if not isinstance(base['room'].get('items'), list):
        base['room']['items'] = list(WORLD_DEFAULT['room']['items'])
    for key in ('hunger', 'happiness', 'energy'):
        base['pet'][key] = max(0, min(100, int(base['pet'].get(key, 80))))
    base['pet']['xp'] = max(0, int(base['pet'].get('xp', 0)))
    base['pet']['level'] = max(1, int(base['pet'].get('level', 1)))
    now = int(time.time()); last = int(base['pet'].get('last_tick') or now)
    hours = max(0, (now - last) // 3600)
    if hours:
        base['pet']['hunger'] = max(0, base['pet']['hunger'] - min(30, hours * 3))
        base['pet']['energy'] = max(0, base['pet']['energy'] - min(30, hours * 2))
        base['pet']['happiness'] = max(0, base['pet']['happiness'] - min(25, hours))
        base['pet']['last_tick'] = now
    return base

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


async def health(request): return web.json_response({'ok':True,'app':'ItzVanyaBot Games Web Apps','ludo_rooms':sum(1 for k in ROOMS if k.startswith('L:')),'uno_rooms':sum(1 for k in ROOMS if k.startswith('U:'))})


async def cleanup_rooms(app):
    while True:
        await asyncio.sleep(300); now=time.time()
        for code,room in list(ROOMS.items()):
            if now-room['updated']>21600: ROOMS.pop(code,None)


async def cleanup_ctx(app):
    task=asyncio.create_task(cleanup_rooms(app))
    try: yield
    finally: task.cancel()


async def start_web_server():
    app=web.Application()
    app.router.add_get('/',health); app.router.add_get('/health',health); app.router.add_get('/api/config',config)
    app.router.add_post('/api/rooms',create_ludo_room); app.router.add_post('/api/uno/rooms',create_uno_room); app.router.add_post('/api/chess/rooms',create_chess_room)
    app.router.add_get('/ludo',ludo_page); app.router.add_get('/ws/ludo/{code}',ludo_ws)
    app.router.add_get('/uno',uno_page); app.router.add_get('/ws/uno/{code}',uno_ws); app.router.add_get('/chess',chess_page); app.router.add_get('/ws/chess/{code}',chess_ws)
    # Vanya World aliases all point to the same 3D page; query ?tab= selects City/Room/Pet.
    world_page = lambda request: web.FileResponse(WEB/'vanya_world.html')
    app.router.add_get('/vanya-city', world_page); app.router.add_get('/world', world_page); app.router.add_get('/vanya-world', world_page)
    app.router.add_get('/city', world_page); app.router.add_get('/room', world_page); app.router.add_get('/pet', world_page)
    app.router.add_get('/api/world/state',world_state); app.router.add_post('/api/world/action',world_action)
    app.router.add_static('/ludo/',WEB,show_index=False); app.router.add_static('/uno/',WEB,show_index=False); app.router.add_static('/chess/',WEB,show_index=False)
    app.cleanup_ctx.append(cleanup_ctx)
    runner=web.AppRunner(app); await runner.setup(); port=int(os.getenv('PORT','8080')); await web.TCPSite(runner,'0.0.0.0',port).start(); return runner
