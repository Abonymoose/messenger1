from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random, string, os

app = Flask(__name__)
socketio = SocketIO(app)

users = {}  # sid -> {"username": ..., "room": ..., "anon": False, "admin": False}
rooms = {"lobby": set()}
challenges = {}  # (challenger_sid, target_sid): game_type
game_rooms = {}  # room_id -> {"type": ..., "players": [...], "data": ...}
user_ranks = {}  # username -> {"rank": int, "admin": bool, "password": str, "scores": {...}}
muted = set()
blocked = set()

def generate_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def handle_connect():
    sid = request.sid
    users[sid] = {"username": "Anonymous", "room": "lobby", "anon": True, "admin": False}
    rooms["lobby"].add(sid)
    join_room("lobby")
    emit("message", {"msg": "System: Anonymous joined the lobby."}, broadcast=True)

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    user = users.get(sid, {})
    room = user.get("room", "lobby")
    rooms.get(room, set()).discard(sid)
    users.pop(sid, None)
    emit("message", {"msg": f"System: {user.get('username', 'Anonymous')} disconnected."}, room=room)

@socketio.on("login")
def handle_login(data):
    sid = request.sid
    username = data["username"]
    password = data["password"]
    if username in user_ranks:
        if user_ranks[username]["password"] != password:
            emit("message", {"msg": "System: Incorrect password."})
            return
    else:
        user_ranks[username] = {"rank": 0, "admin": False, "password": password, "scores": {"roulette": 0, "killspree": 0}}
    users[sid]["username"] = username
    users[sid]["anon"] = False
    users[sid]["admin"] = user_ranks[username]["admin"]
    emit("message", {"msg": f"System: Logged in as {username}."})

@socketio.on("chat")
def handle_chat(data):
    msg = data["msg"].strip()
    sid = request.sid
    user = users[sid]
    username = user["username"]
    room = user["room"]

    if sid in muted:
        emit("message", {"msg": "System: You are muted."})
        return

    # Command parsing
    if msg.startswith("/"):
        handle_command(sid, msg)
        return

    emit("message", {"msg": f"{format_name(username)}: {msg}"}, room=room)

def format_name(username):
    user_data = next((u for u in users.values() if u["username"] == username), None)
    if not user_data:
        return username
    if user_data["anon"]:
        return "Anonymous"
    tag = "[ADMIN]" if user_data["admin"] else f"[{user_ranks[username]['rank']}]"
    return f"{tag}{username}" if not user_data["admin"] else f"[ADMIN]{username}"

def handle_command(sid, msg):
    user = users[sid]
    username = user["username"]
    room = user["room"]
    is_admin = user["admin"]

    args = msg[1:].split()
    cmd = args[0]

    # General commands
    if cmd == "help":
        help_text = (
            "Commands:\n"
            "/help — this list\n"
            "/anon — toggle anonymous mode\n"
            "@username challenge roulette|killspree\n"
            "@username pvc — private chat\n"
            "/rank — show your rank"
        )
        if is_admin:
            help_text += (
                "\n\nAdmin Commands:\n"
                "/kick @user\n/mute @user\n/block @user\n"
                "/rank set @user rank\n"
                "/rank reset @user\n"
                "/admin @user\n"
            )
        emit("message", {"msg": help_text}, room=sid)

    elif cmd == "anon":
        users[sid]["anon"] = not users[sid]["anon"]
        emit("message", {"msg": f"System: {'Anonymous' if users[sid]['anon'] else username} toggled anonymity."}, broadcast=True)

    elif cmd == "rank":
        if user["anon"]:
            emit("message", {"msg": "System: Anonymous users have no rank."})
            return
        score = user_ranks.get(username, {}).get("scores", {})
        emit("message", {"msg": f"System: Rank: {user_ranks[username]['rank']}, Games: {score}"})

    elif cmd == "admin" and is_admin:
        if len(args) >= 2:
            target = args[1].lstrip("@")
            sid2 = find_sid_by_username(target)
            if sid2 and target in user_ranks:
                users[sid2]["admin"] = True
                user_ranks[target]["admin"] = True
                emit("message", {"msg": f"System: {target} is now admin."}, room=sid)

    elif cmd == "kick" and is_admin:
        sid2 = find_sid_by_username(args[1].lstrip("@"))
        if sid2:
            emit("message", {"msg": "System: You were kicked."}, room=sid2)
            socketio.disconnect(sid2)

    elif cmd == "mute" and is_admin:
        sid2 = find_sid_by_username(args[1].lstrip("@"))
        if sid2:
            muted.add(sid2)
            emit("message", {"msg": f"System: Muted {args[1]}."}, room=sid)

    elif cmd == "rank" and len(args) >= 3 and is_admin:
        action, target = args[1], args[2].lstrip("@")
        if action == "reset":
            user_ranks[target]["rank"] = 0
        elif action == "set" and len(args) >= 4:
            user_ranks[target]["rank"] = int(args[3])
        emit("message", {"msg": f"System: Rank updated for {target}."}, room=sid)

    else:
        emit("message", {"msg": f"System: Unknown command '{cmd}'"}, room=sid)

def find_sid_by_username(username):
    for sid, info in users.items():
        if info["username"] == username:
            return sid
    return None

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=4000)
