from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random, string, os

app = Flask(__name__)
socketio = SocketIO(app)

# === Data Storage ===
users = {}  # sid -> username
passwords = { "PM4K": "abonymoose" }  # username -> password
admins = set(["PM4K"])
user_rooms = {}  # sid -> room
anon_users = set()
rooms = {"lobby": set()}
muted = set()
blocked = {}  # username -> set of blocked usernames
challenges = {}  # (challenger_sid, challenged_sid): game_type
pvc_requests = {}  # sid -> target_sid
rankings = {}  # username -> {"rank": 1, "games": {"roulette": 0, "killspree": 0}}

# === Game Rooms ===
game_rooms = {}  # room_id -> {"type": ..., "players": [...], "data": {...}}

# === Helper Functions ===
def generate_room_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_display_name(sid):
    user = users.get(sid, "Anonymous")
    rank = rankings.get(user, {"rank": 1})["rank"]
    prefix = "[ADMIN]" if user in admins else f"[{rank}]"
    return f"{prefix}{user}" if user not in admins else f"{prefix}{user}"

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def on_connect():
    sid = request.sid
    users[sid] = "Anonymous"
    user_rooms[sid] = "lobby"
    rooms["lobby"].add(sid)
    emit("message", {"msg": f"System: Anonymous joined the lobby."}, broadcast=True)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    name = users.get(sid, "Anonymous")
    room = user_rooms.get(sid, "lobby")
    if sid in rooms.get(room, set()):
        rooms[room].remove(sid)
    users.pop(sid, None)
    user_rooms.pop(sid, None)
    anon_users.discard(sid)
    emit("message", {"msg": f"System: {name} left the chat."}, room=room)

@socketio.on("set_username")
def set_username(data):
    sid = request.sid
    name = data.get("username")
    pw = data.get("password")

    if not name or not pw:
        emit("message", {"msg": "System: Username and password required."})
        return

    if name in passwords:
        if passwords[name] != pw:
            emit("message", {"msg": "System: Wrong password."})
            return
    else:
        passwords[name] = pw
        rankings[name] = {"rank": 1, "games": {"roulette": 0, "killspree": 0}}

    users[sid] = name
    anon_users.discard(sid)
    emit("message", {"msg": f"System: Welcome, {get_display_name(sid)}."})

@socketio.on("chat")
def handle_chat(data):
    sid = request.sid
    msg = data["msg"].strip()
    user = users.get(sid, "Anonymous")
    room = user_rooms.get(sid, "lobby")

    if sid in muted:
        emit("message", {"msg": "System: You are muted."})
        return

    if sid in anon_users:
        if msg == "/anon":
            anon_users.remove(sid)
            users[sid] = "Anonymous"
            emit("message", {"msg": "System: You left anonymous mode."}, broadcast=True)
            return
        else:
            emit("message", {"msg": f"Anonymous: {msg}"}, room=room)
            return

    # Command handler
    if msg.startswith("/"):
        handle_command(sid, msg)
    elif msg.startswith("@"):
        handle_at_command(sid, msg)
    else:
        emit("message", {"msg": f"{get_display_name(sid)}: {msg}"}, room=room)
