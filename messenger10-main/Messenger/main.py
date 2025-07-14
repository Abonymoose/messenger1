from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random, string, os

app = Flask(__name__)
socketio = SocketIO(app)

rooms = {"lobby": set()}
users = {}           # sid -> username
user_rooms = {}      # sid -> room
challenges = {}      # (challenger_sid, challenged_sid): game_type
game_rooms = {}      # room_id: {type, players, data}
rankings = {}        # username -> {"roulette": int, "killspree": int, "rank": int}
accounts = {
    "pm4k": {"password": "abonymoose", "admin": True, "rank": 34},
    "ak4k": {"password": "1028", "admin": False, "rank": 1}
}
anon_users = set()
blocked_users = set()
muted_users = set()
admins = {"pm4k"}

@app.route("/")
def index():
    return render_template("index.html")

def generate_room_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

@socketio.on("connect")
def connect():
    users[request.sid] = "Anonymous"
    user_rooms[request.sid] = "lobby"
    rooms["lobby"].add(request.sid)
    emit("message", {"msg": "System: Anonymous joined the chat."}, room="lobby")

@socketio.on("disconnect")
def disconnect():
    sid = request.sid
    name = users.get(sid, "Anonymous")
    room = user_rooms.get(sid, "lobby")
    rooms.get(room, set()).discard(sid)
    users.pop(sid, None)
    user_rooms.pop(sid, None)
    anon_users.discard(sid)
    emit("message", {"msg": f"System: {name} disconnected."}, room=room)

@socketio.on("set_username")
def set_username(data):
    sid = request.sid
    username = data.get("username")
    password = data.get("password")
    if username in accounts:
        if accounts[username]["password"] != password:
            emit("message", {"msg": "System: Incorrect password."})
            return
    else:
        accounts[username] = {"password": password, "admin": False, "rank": 1}
        rankings[username] = {"roulette": 0, "killspree": 0}
    users[sid] = username
    if accounts[username]["admin"]:
        admins.add(username)
    emit("message", {"msg": f"System: Welcome back, {username}!"})

@socketio.on("chat")
def chat(data):
    msg = data["msg"].strip()
    sid = request.sid
    room = user_rooms.get(sid, "lobby")
    username = users.get(sid, "Anonymous")
    is_admin = username in admins

    if sid in muted_users:
        return

    def send(msg): emit("message", {"msg": msg}, room=room)

    if sid in anon_users:
        if msg == "/anon":
            anon_users.discard(sid)
            users[sid] = "Anonymous"
            send("System: Anonymous left anonymous mode.")
        else:
            send(f"Anonymous: {msg}")
        return

    if msg == "/anon":
        users[sid] = "Anonymous"
        anon_users.add(sid)
        send("System: Anonymous joined anonymously.")
        return

    if msg == "/help":
        help_text = (
            "** Commands **\n"
            "/help - Show this\n"
            "/anon - Toggle anonymous mode\n"
            "@user /pvc - Private chat\n"
            "@user /challenge roulette|killspree - Game challenge\n"
            "/pull - Russian Roulette\n"
            "/attack - Killspree\n"
            "/rank - Show your rank"
        )
        if is_admin:
            help_text += (
                "\n** Admin **\n"
                "/kick @user\n"
                "/mute @user\n"
                "/block @user\n"
                "/rank set @user rank\n"
                "/rank reset @user\n"
                "/rename @user newname\n"
                "/game block @user\n"
                "/password check @user\n"
                "/admin @user"
            )
        emit("message", {"msg": help_text})
        return

    if msg.startswith("@") and "/challenge" in msg:
        target, cmd = msg.split("/challenge")
        target = target[1:].strip()
        game = cmd.strip()
        target_sid = next((s for s, u in users.items() if u == target), None)
        if not target_sid:
            send(f"System: User {target} not found.")
            return
        challenges[(sid, target_sid)] = game
        emit("message", {"msg": f"System: {username} challenged you to {game}. Type '/accept' or '/decline'."}, room=target_sid)
        return

    if msg == "/accept":
        for (challenger, challenged), game in list(challenges.items()):
            if challenged == sid:
                new_room = generate_room_id()
                join_room(new_room, sid=challenger)
                join_room(new_room, sid=challenged)
                user_rooms[challenger] = new_room
                user_rooms[challenged] = new_room
                game_rooms[new_room] = {"type": game, "players": [challenger, challenged], "data": {}}
                rooms[new_room] = {challenger, challenged}
                emit("message", {"msg": f"System: Game started - {game}"}, room=new_room)
                if game == "roulette":
                    game_rooms[new_room]["data"] = {"bullet": random.randint(1,6), "turn": 0, "clicks": 0}
                    emit("message", {"msg": "Type /pull to shoot."}, room=new_room)
                elif game == "killspree":
                    game_rooms[new_room]["data"] = {challenger: 3, challenged: 3}
                    emit("message", {"msg": "Type /attack to attack!"}, room=new_room)
                del challenges[(challenger, challenged)]
                return

    if msg == "/decline":
        for pair in list(challenges):
            if pair[1] == sid:
                emit("message", {"msg": "System: Challenge declined."}, room=pair[0])
                del challenges[pair]
                return

    if msg == "/pull":
        if room not in game_rooms or game_rooms[room]["type"] != "roulette": return
        g = game_rooms[room]
        turn = g["data"]["turn"]
        if sid != g["players"][turn % 2]: return
        g["data"]["clicks"] += 1
        if g["data"]["clicks"] == g["data"]["bullet"]:
            winner = g["players"][(turn + 1) % 2]
            emit("message", {"msg": f"{username} got shot! Game over."}, room=room)
            _add_rank(users[winner], "roulette")
            _end_game(room)
        else:
            emit("message", {"msg": f"{username} survived."}, room=room)
            g["data"]["turn"] += 1
        return

    if msg == "/attack":
        if room not in game_rooms or game_rooms[room]["type"] != "killspree": return
        g = game_rooms[room]
        opponent = next(s for s in g["players"] if s != sid)
        g["data"][opponent] -= 1
        emit("message", {"msg": f"{username} attacked! {users[opponent]} has {g['data'][opponent]} HP."}, room=room)
        if g["data"][opponent] <= 0:
            emit("message", {"msg": f"{users[opponent]} defeated!"}, room=room)
            _add_rank(users[sid], "killspree")
            _end_game(room)
        return

    if msg == "/rank":
        if is_admin:
            emit("message", {"msg": "System: Admins don't have rank displayed."})
            return
        r = rankings.get(username, {"roulette": 0, "killspree": 0})
        emit("message", {"msg": f"System: {username} - ROULETTE: {r['roulette']}, KILLSPREE: {r['killspree']}"})
        return

    emit("message", {"msg": f"[{'ADMIN]' if is_admin else rankings.get(username, {}).get('rank', 1)}]{username}: {msg}"}, room=room)

def _end_game(room):
    for sid in rooms.get(room, set()):
        join_room("lobby", sid=sid)
        user_rooms[sid] = "lobby"
    rooms.pop(room, None)
    game_rooms.pop(room, None)

def _add_rank(username, game):
    if username not in rankings:
        rankings[username] = {"roulette": 0, "killspree": 0}
    rankings[username][game] += 1

# Final server run
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=4000)
