from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string

app = Flask(__name__)
socketio = SocketIO(app)

# --- Global State ---
rooms = {"lobby": set()}
users = {}              # sid -> username
user_rooms = {}         # sid -> room
challenges = {}         # (challenger_sid, challenged_sid): game_type
game_rooms = {}         # room_id -> game state
rankings = {}           # username -> score dict

# --- Helpers ---
def generate_room_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def close_game_room(room):
    for sid in rooms.get(room, set()):
        user_rooms[sid] = "lobby"
        join_room("lobby", sid=sid)
    rooms.pop(room, None)
    game_rooms.pop(room, None)

# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html")

# --- Socket Events ---
@socketio.on("connect")
def handle_connect():
    sid = request.sid
    users[sid] = "Anonymous"
    user_rooms[sid] = "lobby"
    rooms["lobby"].add(sid)
    join_room("lobby")
    emit("message", {"msg": f"System: Anonymous joined the lobby."}, room="lobby")

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    username = users.get(sid, "Anonymous")
    room = user_rooms.get(sid, "lobby")
    rooms.get(room, set()).discard(sid)
    users.pop(sid, None)
    user_rooms.pop(sid, None)
    emit("message", {"msg": f"System: {username} disconnected."}, room=room)

@socketio.on("set_username")
def set_username(data):
    sid = request.sid
    newname = data["username"]
    users[sid] = newname
    emit("message", {"msg": f"System: You are now known as {newname}."}, room=sid)

@socketio.on("chat")
def chat(data):
    sid = request.sid
    room = user_rooms.get(sid, "lobby")
    username = users.get(sid, "Anonymous")
    msg = data["msg"].strip()

    if msg.startswith("@") and " " in msg:
        target_name, command = msg[1:].split(" ", 1)
        target_sid = next((s for s, u in users.items() if u == target_name), None)
        if not target_sid:
            emit("message", {"msg": f"System: User '{target_name}' not found."}, room=sid)
            return

        if command == "challenge":
            challenges[(sid, target_sid)] = "roulette"
            emit("message", {"msg": f"System: {username} challenged you to Russian Roulette. Type 'accept' or 'decline'."}, room=target_sid)
        elif command == "killspree":
            challenges[(sid, target_sid)] = "killspree"
            emit("message", {"msg": f"System: {username} challenged you to Killspree. Type 'accept' or 'decline'."}, room=target_sid)
        return

    elif msg == "accept":
        for (challenger_sid, challenged_sid), game in list(challenges.items()):
            if challenged_sid == sid:
                new_room = generate_room_id()
                game_rooms[new_room] = {"type": game, "players": [challenger_sid, challenged_sid], "data": {}}
                user_rooms[challenger_sid] = new_room
                user_rooms[challenged_sid] = new_room
                rooms.setdefault(new_room, set()).update([challenger_sid, challenged_sid])
                join_room(new_room, sid=challenger_sid)
                join_room(new_room, sid=challenged_sid)

                emit("message", {"msg": f"System: Game '{game}' started in room {new_room}."}, room=new_room)
                if game == "roulette":
                    game_rooms[new_room]["data"] = {"bullet": random.randint(1, 6), "turn": 0, "clicks": 0}
                    emit("message", {"msg": f"System: Russian Roulette. Type 'pull' to shoot."}, room=new_room)
                elif game == "killspree":
                    game_rooms[new_room]["data"] = {challenger_sid: 3, challenged_sid: 3}
                    emit("message", {"msg": f"System: Killspree. Type 'attack' to fight."}, room=new_room)
                del challenges[(challenger_sid, challenged_sid)]
                return

    elif msg == "decline":
        for pair in list(challenges):
            if pair[1] == sid:
                emit("message", {"msg": f"System: Challenge declined."}, room=pair[0])
                del challenges[pair]
                return

    elif msg == "pull":
        if room not in game_rooms or game_rooms[room]["type"] != "roulette": return
        game = game_rooms[room]
        players = game["players"]
        turn = game["data"]["turn"]
        if sid != players[turn % 2]: return

        game["data"]["clicks"] += 1
        if game["data"]["clicks"] == game["data"]["bullet"]:
            emit("message", {"msg": f"System: {username} got shot. Game over."}, room=room)
            winner_sid = players[(turn + 1) % 2]
            rankings.setdefault(users[winner_sid], {"roulette": 0, "killspree": 0})["roulette"] += 1
            close_game_room(room)
        else:
            emit("message", {"msg": f"System: {username} survived."}, room=room)
            game["data"]["turn"] += 1
        return

    elif msg == "attack":
        if room not in game_rooms or game_rooms[room]["type"] != "killspree": return
        game = game_rooms[room]
        opponent_sid = next(s for s in game["players"] if s != sid)
        game["data"][opponent_sid] -= 1
        emit("message", {"msg": f"System: {username} attacked! {users[opponent_sid]} has {game['data'][opponent_sid]} HP left."}, room=room)
        if game["data"][opponent_sid] <= 0:
            emit("message", {"msg": f"System: {users[opponent_sid]} has been defeated!"}, room=room)
            rankings.setdefault(users[sid], {"roulette": 0, "killspree": 0})["killspree"] += 1
            close_game_room(room)
        return

    elif msg == "@rank":
        r = rankings.get(username, {"roulette": 0, "killspree": 0})
        emit("message", {"msg": f"System: {username} Rankings — Roulette: {r['roulette']}, Killspree: {r['killspree']}"}, room=sid)
        return

    elif msg == "/help":
        help_text = (
            "Commands:\n"
            "@username challenge — Russian Roulette\n"
            "@username killspree — Killspree\n"
            "accept / decline — respond to challenge\n"
            "pull — for Russian Roulette\n"
            "attack — for Killspree\n"
            "@rank — view your rank\n"
            "/help — view this list"
        )
        emit("message", {"msg": help_text}, room=sid)
        return

    # Broadcast regular message
    emit("message", {"msg": f"{username}: {msg}"}, room=room)

# --- Entry ---
if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
