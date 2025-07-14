import os, random, string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import eventlet

# === Initialize Flask & SocketIO ===
app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')

# === In‑memory Data Stores ===
rooms = {"lobby": set()}
users = {}         # sid -> username
user_rooms = {}    # sid -> room
anon_users = set()
accounts = {
    "pm4k": {"password": "abonymoose", "admin": True, "rank": 34},
    "ak4k": {"password": "1028", "admin": False, "rank": 1},
}
rankings = {u: {"roulette": 0, "killspree": 0} for u in accounts}
challenges = {}     # (challenger_sid, challenged_sid): game_name
game_rooms = {}     # room_id -> {type, players, data}
muted, blocked = set(), set()
admins = {u for u,d in accounts.items() if d["admin"]}

@app.route("/")
def index():
    return render_template("index.html")

def gen_room():
    return ''.join(random.choices(string.ascii_letters+string.digits, k=8))

def display_name(sid):
    u = users.get(sid, "Anonymous")
    if u in admins:
        return f"[ADMIN]{u}"
    return f"[{accounts[u]['rank']}]"+u

# === WebSocket Events ===
@socketio.on("connect")
def on_connect():
    sid = request.sid
    users[sid] = "Anonymous"
    user_rooms[sid] = "lobby"
    rooms["lobby"].add(sid)
    emit("message", {"msg": "System: An Anonymous joined."}, broadcast=True)
    emit("active_count", {"n": len(users)}, broadcast=True)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    u = users.get(sid, "Anonymous")
    room = user_rooms.get(sid, "lobby")
    rooms.get(room, set()).discard(sid)
    users.pop(sid, None)
    user_rooms.pop(sid, None)
    anon_users.discard(sid)
    emit("message", {"msg": f"System: {u} left."}, broadcast=True)
    emit("active_count", {"n": len(users)}, broadcast=True)

@socketio.on("set_username")
def on_set_user(data):
    sid = request.sid
    nm, pw = data.get("username"), data.get("password")
    if not nm or not pw:
        emit("message", {"msg": "System: Username & password required."})
        return
    if nm in accounts:
        if accounts[nm]["password"] != pw:
            emit("message", {"msg": "System: Wrong password."}); return
    else:
        accounts[nm] = {"password": pw, "admin": False, "rank": 1}
        rankings[nm] = {"roulette":0, "killspree":0}
    users[sid] = nm
    anon_users.discard(sid)
    if accounts[nm]["admin"]:
        admins.add(nm)
    rooms["lobby"].add(sid)
    emit("message", {"msg": f"System: Welcome {display_name(sid)}!"}, room=user_rooms[sid])
    emit("active_count", {"n": len(users)}, broadcast=True)

@socketio.on("chat")
def on_chat(data):
    sid = request.sid
    msg = data.get("msg","").strip()
    room = user_rooms.get(sid, "lobby")
    u = users.get(sid,"Anonymous")
    is_admin = u in admins
    def reply(t): emit("message", {"msg": t}, room=room)

    if sid in muted:
        return

    if sid in anon_users:
        if msg == "/anon":
            anon_users.discard(sid)
            users[sid] = "Anonymous"
            reply("System: You left anonymous mode.")
        else:
            reply(f"Anonymous: {msg}")
        return

    if msg == "/anon":
        users[sid] = "Anonymous"
        anon_users.add(sid)
        rooms["lobby"].add(sid)
        reply("System: You joined anonymous mode.")
        return

    if msg == "/help":
        cmd = (
            "/help\n/anon\n@user /pvc\n@user /challenge roulette|killspree\n"
            "/pull /attack /rank"
        )
        if is_admin:
            cmd += "\nAdmin: /kick @user /mute @user /block @user"                   " /rank set @user X /rank reset @user"                   " /rename @user newname /game block @user"                   " /password check @user /admin @user"
        reply(cmd); return

    if msg == "/active":
        reply(f"System: Active users: {len(users)}")
        return

    if msg == "/rank":
        if is_admin:
            reply("System: Admins don't show rank.")
        else:
            r = rankings.get(u, {})
            reply(f"System: {u} → Roulette: {r.get('roulette',0)}, Killspree: {r.get('killspree',0)}")
        return

    if is_admin and msg.startswith("/"):
        parts = msg.split()
        cmd, rest = parts[0], parts[1:]
        if cmd == "/kick" and rest:
            t = rest[0].lstrip("@")
            tsid = next((s for s,k in users.items() if k==t),None)
            if tsid: socketio.server.disconnect(tsid)
            return
        if cmd == "/mute" and rest:
            t=rest[0].lstrip("@")
            tsid=next((s for s,k in users.items() if k==t),None)
            if tsid: muted.add(tsid)
            return
        if cmd == "/block" and rest:
            blocked.add(rest[0].lstrip("@"))
            return
        if cmd == "/rank" and rest[0] in ("set","reset"):
            t=rest[1].lstrip("@"); val=int(rest[2])
            if t in accounts: accounts[t]["rank"]=val
            return
        if cmd == "/rename" and len(rest)>=2:
            t=rest[0].lstrip("@"); new=rest[1]
            for s,k in list(users.items()):
                if k==t: users[s]=new
            return
        if cmd == "/game" and rest and rest[0]=="block":
            blocked.add(rest[1].lstrip("@"))
            return
        if cmd == "/password" and rest and rest[0]=="check":
            t=rest[1].lstrip("@")
            pw=accounts.get(t,{}).get("password")
            if pw: reply(f"System: {t}'s password is {pw}")
            return
        if cmd == "/admin" and rest:
            t=rest[0].lstrip("@")
            if t in accounts:
                accounts[t]["admin"]=True; admins.add(t)
            return

    if msg.startswith("@") and "/challenge" in msg:
        parts=msg.split()
        target=parts[0][1:]; game=parts[-1]
        tsid=next((s for s,k in users.items() if k==target),None)
        if tsid and target not in blocked:
            challenges[(sid,tsid)]=game
            emit("message", {"msg":f"System: {u} challenged {target} to {game}. Type '/accept' or '/decline'."}, room=tsid)
        return

    if msg == "/accept":
        match=[(c,t,g) for (c,t),g in challenges.items() if t==sid]
        if not match: return
        c,t,g=match[0]
        rid=gen_room()
        for p in (c,t):
            leave_room(user_rooms[p],sid=p)
            user_rooms[p]=rid
            join_room(rid,sid=p)
        game_rooms[rid]={"type":g,"players":[c,t],"data":{}}
        rooms[rid]={c,t}
        emit("message",{"msg":f"System: Started game: {g}"},room=rid)
        if g=="roulette":
            game_rooms[rid]["data"]={"bullet":random.randint(1,6),"turn":0,"clicks":0}
            emit("message",{"msg":"Type /pull"},room=rid)
        elif g=="killspree":
            game_rooms[rid]["data"]={c:3,t:3}
            emit("message",{"msg":"Type /attack"},room=rid)
        del challenges[(c,t)]
        return

    if msg == "/decline":
        for pair in list(challenges):
            if pair[1]==sid:
                emit("message",{"msg":"System: Challenge declined."},room=pair[0])
                del challenges[pair]
                break
        return

    if msg == "/pull":
        roomg=game_rooms.get(room)
        if roomg and roomg["type"]=="roulette":
            d=roomg["data"]; turn=d["turn"]; ps=roomg["players"]
            if sid!=ps[turn%2]: return
            d["clicks"]+=1
            if d["clicks"]==d["bullet"]:
                emit("message",{"msg":f"{u} got shot!"},room=room)
                rankings[users[ps[(turn+1)%2]]]["roulette"]+=1
                _end_game(room); return
            else:
                emit("message",{"msg":f"{u} survived."},room=room)
                d["turn"]+=1
        return

    if msg == "/attack":
        roomg=game_rooms.get(room)
        if roomg and roomg["type"]=="killspree":
            d=roomg["data"]; opp=next(p for p in roomg["players"] if p!=sid)
            d[opp]-=1
            emit("message",{"msg":f"{u} attacked. {users[opp]} HP: {d[opp]}."},room=room)
            if d[opp]<=0:
                emit("message",{"msg":f"{users[opp]} defeated!"},room=room)
                rankings[u]["killspree"]+=1
                _end_game(room)
        return

    emit("message",{"msg":f"{display_name(sid)}: {msg}"},room=room)

def _end_game(r):
    for s in rooms.get(r,()):
        leave_room(r,sid=s); join_room("lobby",sid=s); user_rooms[s]="lobby"
    rooms.pop(r,None); game_rooms.pop(r,None)

if __name__=="__main__":
    port=int(os.environ.get("PORT",4000))
    socketio.run(app,host="0.0.0.0",port=port)
