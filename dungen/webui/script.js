import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { io } from 'socket.io-client';
import 'xterm/css/xterm.css';

class DungenWebUI {
    constructor() {
        this.terminal = null;
        this.socket = null;
        this.gameRunning = false;
        this.inputBuffer = '';
        this.waitingForInput = false;
        this.mapTilesContainer = null;
        this.mapRefreshInterval = null;
        this.init();
    }

    init() {
        this.initTerminal();
        this.initSocket();
        this.bindEvents();
        this.mapTilesContainer = document.getElementById('map-tiles-container');
        this.loadMapTiles();
    }

    initTerminal() {
        this.terminal = new Terminal({
            cursorBlink: true,
            convertEol: true,
            cursorStyle: 'block',
            fontFamily: 'monospace',
            fontSize: 10,
            theme: {
                background: '#000000',
                foreground: '#ffffff',
                cursor: '#00cc66',
                selection: '#00cc66',
                black: '#000000',
                red: '#ff6565',
                green: '#00cc66',
                brightBlack: '#333333',
                brightRed: '#ff6565',
                brightGreen: '#00cc66',
            },
            scrollback: 1000
        });

        this.terminal.open(document.getElementById('terminal'));
        
        const fitAddon = new FitAddon();
        this.terminal.loadAddon(fitAddon);
        fitAddon.fit();

        window.addEventListener('resize', () => {
            fitAddon.fit();
        });

        this.terminal.onResize(({ cols, rows }) => {
            if (this.socket && this.socket.connected) {
                this.socket.emit('resize', { cols, rows });
            }
        });

        this.terminal.onData(data => {
            console.log('[INPUT] ', data);
            
            if (!this.gameRunning) {
                return;
            }

            switch (data) {
                case '\r':
                case '\n':
                    if (this.inputBuffer.trim()) {
                        this.socket.emit('game_input', this.inputBuffer + '\n');
                        this.terminal.write('\r\n\r\n');
                        this.inputBuffer = '';
                    } else {
                        this.terminal.write('\r\n\r\n');
                    }
                    break;
                case '\u007f':
                case '\b':
                    if (this.inputBuffer.length > 0) {
                        this.inputBuffer = this.inputBuffer.slice(0, -1);
                        this.terminal.write('\b \b');
                    }
                    break;
                default:
                    if (data >= ' ' && data.length === 1) {
                        this.inputBuffer += data;
                        this.terminal.write(data);
                    }
                    break;
            }
        });

        this.terminal.focus();
    }

    initSocket() {
        this.socket = io();
        
        this.socket.on('connect', () => {
            this.terminal.writeln('\r\n\x1b[32mCONNECTED TO DUNGEN!\x1b[0m\r\n');
            if (this.terminal) {
                this.socket.emit('resize', { cols: this.terminal.cols, rows: this.terminal.rows });
            }
        });

        this.socket.on('disconnect', () => {
            this.terminal.writeln('\r\n\x1b[31mDISCONNECTED\x1b[0m\r\n');
            this.gameRunning = false;
            this.updateButtons();
        });

        this.socket.on('game_output', (data) => {
            this.terminal.write(data);
        });

        this.socket.on('game_started', () => {
            this.gameRunning = true;
            this.updateButtons();
        });

        this.socket.on('game_stopped', () => {
            this.gameRunning = false;
            this.updateButtons();
        });

        this.socket.on('error', (error) => {
            this.terminal.writeln(`\r\n\x1b[31m[ERROR] ${error}\x1b[0m`);
        });
    }

    bindEvents() {
        const startBtn = document.getElementById('start-game');
        const endBtn = document.getElementById('end-game');

        startBtn.addEventListener('click', () => this.startGame());
        startBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.startGame();
        });

        endBtn.addEventListener('click', () => this.stopGame());
        endBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.stopGame();
        });

        document.getElementById('terminal').addEventListener('click', () => {
            this.terminal.focus();
        });

        document.addEventListener('keydown', (e) => {
            if (this.terminal && document.activeElement === document.getElementById('terminal')) {
                console.log('[KEYDOWN]', e.key);
            }
        });
    }

    async loadMapTiles() {
        try {
            const response = await fetch('/api/map-tiles');
            const tiles = await response.json();
            this.displayMapTiles(tiles);
        } catch (error) {
            console.error('Failed to load map tiles:', error);
        }
    }

    displayMapTiles(tiles) {
        this.mapTilesContainer.innerHTML = '';
        
        tiles.forEach(tile => {
            const tileElement = document.createElement('img');
            tileElement.src = `/assets/mini-map/${tile}`;
            tileElement.className = 'map-tile';
            tileElement.alt = `Map tile ${tile}`;
            tileElement.title = `Turn ${tile.split('_')[1].split('.')[0]}`;
            this.mapTilesContainer.appendChild(tileElement);
        });
    }

    startGame() {
        const gameSettings = document.getElementById('game-settings').value;
        const dimensions = { cols: this.terminal.cols, rows: this.terminal.rows };
        this.socket.emit('start_game', { 
            settings: gameSettings, 
            dimensions: dimensions,
            mapGen: true
        });
        
        this.mapTilesContainer.innerHTML = '';

        this.startMapRefresh();
    }

    stopGame() {
        if (this.gameRunning) {
            this.socket.emit('stop_game');
        }
        this.terminal.write('\r\n');
        this.terminal.writeln('\r\n\x1b[33mFarewell, adventurer!\x1b[0m');
        
        this.mapTilesContainer.innerHTML = '';
        
        this.stopMapRefresh();
    }

    startMapRefresh() {
        this.stopMapRefresh();
        this.mapRefreshInterval = setInterval(() => {
            this.loadMapTiles();
        }, 2000);
    }

    stopMapRefresh() {
        if (this.mapRefreshInterval) {
            clearInterval(this.mapRefreshInterval);
            this.mapRefreshInterval = null;
        }
    }

    updateButtons() {
        const startBtn = document.getElementById('start-game');
        const endBtn = document.getElementById('end-game');
        startBtn.disabled = this.gameRunning;
        endBtn.disabled = !this.gameRunning;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new DungenWebUI();
});