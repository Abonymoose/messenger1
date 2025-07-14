from flask import Flask, render_template, request, jsonify
import random
import time

app = Flask(__name__)
username = "Guest"
anon_mode = False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/terminal", methods=["POST"])
def terminal():
    global username, anon_mode
    cmd = request.json.get("command", "").strip().lower()
    output = ""

    # Handle commands
    if cmd == "help":
        output = (
            "Messenger10 Terminal - Help Menu\n"
            "Available commands:\n"
            " - help: Show this help screen\n"
            " - username <name>: Change your username\n"
            " - anon: Toggle anonymous mode\n"
            " - chat: Enter chat mode (placeholder)\n"
            " - game: Play a game\n"
            " - clear: Clear the screen\n"
            " - credits: Show creator info\n"
        )
    elif cmd.startswith("username "):
        username = cmd.split(" ", 1)[1]
        anon_mode = False
        output = f"Username set to: {username}"
    elif cmd == "anon":
        anon_mode = not anon_mode
        output = f"Anonymous mode {'enabled' if anon_mode else 'disabled'}"
    elif cmd == "chat":
        output = "Chat mode is under development. Type 'help' for options."
    elif cmd == "game":
        output = (
            "Launching game menu...\n"
            "Available games:\n"
            " - russian\n"
            " - zombie\n"
            " - fight\n"
            "Type the game name to begin."
        )
    elif cmd == "russian":
        output = "Russian Roulette Game launching... (add code logic here)"
    elif cmd == "zombie":
        output = "Zombie Apocalypse Game launching... (add code logic here)"
    elif cmd == "fight":
        output = "KillSpree Fight Game launching... (add code logic here)"
    elif cmd == "credits":
        output = (
            "Messenger10 coded by pm4k\n"
            "YouTube: https://www.youtube.com/@pm4k\n"
            "Instagram: https://www.instagram.com/p4r5hv/"
        )
    elif cmd == "clear":
        output = ""
    else:
        output = f"Command '{cmd}' not recognized. Type 'help' for options."

    prefix = "[Anonymous]" if anon_mode else f"[{username}]"
    return jsonify({"response": f"{prefix} > {cmd}\n{output}"})


if __name__ == "__main__":
    app.run(debug=True)
