import os
import sys
import threading
import queue
import io
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import subprocess
import signal

# Add the parent directory to the path so we can import the game module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dungen-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

class GameProcess:
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.running = False
        self.thread = None

    def start(self, settings_file):
        if self.running:
            return False
        
        # Get the path to the game script
        game_script = os.path.join(os.path.dirname(__file__), '..', 'game.py')
        settings_path = os.path.join(os.path.dirname(__file__), '..', '..', settings_file)
        
        # Check if settings file exists
        if not os.path.exists(settings_path):
            raise FileNotFoundError(f"Settings file not found: {settings_path}")
        
        # Start the game process
        self.process = subprocess.Popen(
            [sys.executable, game_script, '--settings', settings_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        self.running = True
        
        # Start output reading thread
        self.thread = threading.Thread(target=self._read_output)
        self.thread.daemon = True
        self.thread.start()
        
        return True

    def stop(self):
        if not self.running:
            return
        
        self.running = False
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            finally:
                self.process = None

    def _read_output(self):
        while self.running and self.process:
            try:
                line = self.process.stdout.readline()
                if line:
                    self.output_queue.put(line)
                else:
                    break
            except Exception as e:
                print(f"Error reading output: {e}")
                break
        
        self.running = False

    def send_input(self, data):
        if self.running and self.process:
            try:
                self.process.stdin.write(data)
                self.process.stdin.flush()
            except Exception as e:
                print(f"Error sending input: {e}")

# Global game process instance
game_process = GameProcess()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/script.js')
def script():
    return send_from_directory('.', 'script.js')

@app.route('/node_modules/<path:filename>')
def node_modules(filename):
    return send_from_directory('node_modules', filename)

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('game_output', '\r\nWelcome to DUNGEN Web UI!\r\n')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('start_game')
def handle_start_game(data):
    try:
        settings_file = data.get('settings', 'fantasy.yaml')
        
        if game_process.start(settings_file):
            emit('game_started')
            emit('game_output', f'\r\nStarting DUNGEN with {settings_file}...\r\n')
            
            # Start a thread to forward game output to the client
            def forward_output():
                while game_process.running:
                    try:
                        output = game_process.output_queue.get(timeout=0.1)
                        socketio.emit('game_output', output)
                    except queue.Empty:
                        continue
                    except Exception as e:
                        print(f"Error forwarding output: {e}")
                        break
            
            output_thread = threading.Thread(target=forward_output)
            output_thread.daemon = True
            output_thread.start()
        else:
            emit('error', 'Game is already running')
    except Exception as e:
        emit('error', f'Failed to start game: {str(e)}')

@socketio.on('stop_game')
def handle_stop_game():
    game_process.stop()
    emit('game_stopped')
    emit('game_output', '\r\nGame stopped\r\n')

@socketio.on('game_input')
def handle_game_input(data):
    if game_process.running:
        game_process.send_input(data)
    else:
        emit('error', 'No game is currently running')

if __name__ == '__main__':
    print("Starting DUNGEN Web UI server...")
    print("Open your browser to http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)