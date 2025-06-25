class DungenWebUI {
    constructor() {
        this.terminal = null;
        this.socket = null;
        this.gameRunning = false;
        this.init();
    }

    init() {
        this.initTerminal();
        this.initSocket();
        this.bindEvents();
    }

    initTerminal() {
        this.terminal = new Terminal({
            cursorBlink: true,
            theme: {
                background: '#000000',
                foreground: '#00ff00',
                cursor: '#00ff00',
                selection: '#00ff00',
                black: '#000000',
                red: '#ff0000',
                green: '#00ff00',
                yellow: '#ffff00',
                blue: '#0000ff',
                magenta: '#ff00ff',
                cyan: '#00ffff',
                white: '#ffffff',
                brightBlack: '#666666',
                brightRed: '#ff6666',
                brightGreen: '#66ff66',
                brightYellow: '#ffff66',
                brightBlue: '#6666ff',
                brightMagenta: '#ff66ff',
                brightCyan: '#66ffff',
                brightWhite: '#ffffff'
            },
            fontSize: 14,
            fontFamily: 'Courier New, monospace',
            rows: 30,
            cols: 100
        });

        this.terminal.open(document.getElementById('terminal'));
        
        // Add fit addon for responsive terminal
        const fitAddon = new FitAddon.FitAddon();
        this.terminal.loadAddon(fitAddon);
        fitAddon.fit();

        // Handle window resize
        window.addEventListener('resize', () => {
            fitAddon.fit();
        });

        // Handle terminal input
        this.terminal.onData(data => {
            if (this.socket && this.gameRunning) {
                this.socket.emit('game_input', data);
            }
        });
    }

    initSocket() {
        this.socket = io();
        
        this.socket.on('connect', () => {
            this.terminal.writeln('\r\n\x1b[32mConnected to DUNGEN server\x1b[0m');
        });

        this.socket.on('disconnect', () => {
            this.terminal.writeln('\r\n\x1b[31mDisconnected from DUNGEN server\x1b[0m');
            this.gameRunning = false;
            this.updateButtons();
        });

        this.socket.on('game_output', (data) => {
            this.terminal.write(data);
        });

        this.socket.on('game_started', () => {
            this.gameRunning = true;
            this.updateButtons();
            this.terminal.writeln('\r\n\x1b[32mGame started!\x1b[0m');
        });

        this.socket.on('game_stopped', () => {
            this.gameRunning = false;
            this.updateButtons();
            this.terminal.writeln('\r\n\x1b[31mGame stopped\x1b[0m');
        });

        this.socket.on('error', (error) => {
            this.terminal.writeln(`\r\n\x1b[31mError: ${error}\x1b[0m`);
        });
    }

    bindEvents() {
        document.getElementById('start-game').addEventListener('click', () => {
            this.startGame();
        });

        document.getElementById('stop-game').addEventListener('click', () => {
            this.stopGame();
        });

        document.getElementById('clear-terminal').addEventListener('click', () => {
            this.terminal.clear();
        });
    }

    startGame() {
        const gameSettings = document.getElementById('game-settings').value;
        this.socket.emit('start_game', { settings: gameSettings });
    }

    stopGame() {
        this.socket.emit('stop_game');
    }

    updateButtons() {
        const startBtn = document.getElementById('start-game');
        const stopBtn = document.getElementById('stop-game');
        
        startBtn.disabled = this.gameRunning;
        stopBtn.disabled = !this.gameRunning;
    }
}

// Initialize the web UI when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new DungenWebUI();
});