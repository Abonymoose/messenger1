from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('join')
def handle_join():
    sid = request.sid
    code = f"User{random.randint(1000, 9999)}"
    users[sid] = code
    emit('user_code', code)
    emit('chat', {'msg': f"{code} has joined the chat."}, broadcast=True)
    emit('active_users', list(users.values()), broadcast=True)

@socketio.on('chat')
def handle_chat(data):
    sid = request.sid
    code = users.get(sid, "Unknown")
    msg = data.get('msg', '')
    emit('chat', {'msg': f"{code}: {msg}"}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    code = users.pop(sid, "Unknown")
    emit('chat', {'msg': f"{code} has left the chat."}, broadcast=True)
    emit('active_users', list(users.values()), broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
