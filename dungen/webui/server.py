import os
import sys
import threading
import queue
import fcntl
import termios
import struct
import select
import subprocess
import pty
import shutil
from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit
import glob
import json


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


def remove_map_tiles():
    root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
    tiles_dir = os.path.join(root_dir, 'assets', 'mini-map')
    
    tile_files = glob.glob(os.path.join(tiles_dir, 'tile_*.png'))
    for tile_file in tile_files:
        os.remove(tile_file)


class GameProcess:
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.master_fd = None

    def start(self, settings_file, dimensions, map_gen=False):
        if self.running:
            return False
        
        if map_gen:
            remove_map_tiles()
        
        game_script = os.path.join(os.path.dirname(__file__), '..', 'main.py')
        root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
        settings_path = os.path.join(root_dir, settings_file)
        
        pid, self.master_fd = pty.fork()

        if pid == 0:
            os.chdir(root_dir)
            cmd = [sys.executable, game_script, '--settings', settings_path, '--vllm', '--webui']
            if map_gen:
                cmd.append('--map')
            os.execvp(cmd[0], cmd)
        else:
            self.process = pid
        
            attr = termios.tcgetattr(self.master_fd)
            attr[3] = attr[3] & ~termios.ECHO
            termios.tcsetattr(self.master_fd, termios.TCSANOW, attr)

            self.resize(dimensions)

            self.running = True
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
                os.kill(self.process, 9)
                os.waitpid(self.process, 0)
            except OSError:
                pass
            self.process = None
        
        if self.master_fd:
            os.close(self.master_fd)
            self.master_fd = None

    def _read_output(self):
        while self.running and self.master_fd:
            r, _, _ = select.select([self.master_fd], [], [], 0.1)
            if r:
                try:
                    data = os.read(self.master_fd, 1024)
                    if data:
                        self.output_queue.put(data.decode('utf-8', 'ignore'))
                    else:
                        break
                except OSError:
                    break
        self.running = False

    def send_input(self, data):
        if self.running and self.master_fd:
            os.write(self.master_fd, data.encode('utf-8'))

    def resize(self, dimensions):
        if self.master_fd:
            rows = dimensions.get('rows', 24)
            cols = dimensions.get('cols', 80)
            
            size = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)


game_process = GameProcess()


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/dist/<path:filename>')
def dist(filename):
    return send_from_directory('dist', filename)


@app.route('/assets/mini-map/<path:filename>')
def serve_map_tiles(filename):
    root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
    return send_from_directory(os.path.join(root_dir, 'assets', 'mini-map'), filename)


@app.route('/api/map-tiles')
def get_map_tiles():
    root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
    tiles_dir = os.path.join(root_dir, 'assets', 'mini-map')
    tile_files = glob.glob(os.path.join(tiles_dir, 'tile_*.png'))
    tile_files.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]))
    tiles = [os.path.basename(f) for f in tile_files]
    return json.dumps(tiles)


@socketio.on('connect')
def handle_connect():
    print('[CLIENT CONNECTED]')


@socketio.on('disconnect')
def handle_disconnect():
    print('[CLIENT DISCONNECTED]')


@socketio.on('start_game')
def handle_start_game(data):
    settings_file = data.get('settings', 'fantasy.yaml')
    dimensions = data.get('dimensions', {'cols': 80, 'rows': 24})
    map_gen = data.get('mapGen', False)
    
    if game_process.start(settings_file, dimensions, map_gen):
        emit('game_started')
        
        def forward_output():
            while game_process.running:
                try:
                    output = game_process.output_queue.get(timeout=0.1)
                    socketio.emit('game_output', output)
                except queue.Empty:
                    continue
        
        output_thread = threading.Thread(target=forward_output)
        output_thread.daemon = True
        output_thread.start()


@socketio.on('stop_game')
def handle_stop_game():
    game_process.stop()

    remove_map_tiles()
    
    emit('game_stopped')


@socketio.on('game_input')
def handle_game_input(data):
    if game_process.running:
        game_process.send_input(data)


@socketio.on('resize')
def handle_resize(data):
    if game_process.running:
        game_process.resize({'cols': data['cols'], 'rows': data['rows']})


if __name__ == '__main__':
    print("Starting DUNGEN! Web UI server...")
    print("Open your browser to http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)