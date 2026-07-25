// SigmX desktop client — Electron main process.
//
// Spawns the Python backend (vibe-trading serve) as a sidecar, waits for its
// /health endpoint, then opens a native window pointed at the served UI.
// The backend runs in DESKTOP_MODE (loopback skips JWT auth) and with the
// inline market-sync worker, so this single Electron process is the whole app:
// it both pulls A-share data and serves the dashboard.
//
// Dev mode (SIGMX_DEV=1): spawn the backend from source via `python -m api_server`.
// Production (default): spawn the PyInstaller-bundled executable in resources/python-dist.

const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const net = require('net');

const PORT = parseInt(process.env.SIGMX_PORT || '8899', 10);
const HOST = '127.0.0.1';
const isDev = !!process.env.SIGMX_DEV;

let backendProc = null;
let mainWindow = null;

// Resolve the Python backend executable.
//   dev:      python -m api_server   (from the repo's agent/ dir)
//   packaged: <resources>/python-dist/vibe-trading(.exe) serve
function resolveBackendCommand() {
  if (isDev) {
    const repoAgent = path.resolve(__dirname, '..', 'agent');
    return {
      cmd: process.env.SIGMX_PYTHON || 'python',
      args: ['-m', 'api_server'],
      cwd: repoAgent,
      label: 'python -m api_server (dev)',
    };
  }
  const ext = process.platform === 'win32' ? '.exe' : '';
  // PyInstaller onedir layout: python-dist/vibe-trading/vibe-trading(.exe)
  const bundled = path.join(
    process.resourcesPath, 'python-dist', 'vibe-trading', `vibe-trading${ext}`,
  );
  return {
    cmd: bundled,
    args: ['--port', String(PORT), '--host', HOST],
    cwd: path.dirname(bundled),
    label: `${bundled} serve`,
  };
}

function spawnBackend() {
  const { cmd, args, cwd, label } = resolveBackendCommand();
  console.log(`[sigmx] starting backend: ${label}`);

  const env = {
    ...process.env,
    // Desktop mode: loopback skips auth; inline worker pulls data.
    VIBE_TRADING_DESKTOP_MODE: '1',
    VIBE_TRADING_START_MARKET_SYNC_WORKER: '1',
    VIBE_TRADING_PORT: String(PORT),
    VIBE_TRADING_HOST: HOST,
  };
  // Packaged/desktop uses the default data home (~/.vibe-trading/market.db).
  // Dev users can override with SIGMX_DB_PATH if they have a separate data dir.
  if (isDev && process.env.SIGMX_DB_PATH) {
    env.VIBE_TRADING_MARKET_DB_PATH = process.env.SIGMX_DB_PATH;
  }

  backendProc = spawn(cmd, args, { cwd, env, windowsHide: true });
  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code, signal) => {
    console.log(`[sigmx] backend exited code=${code} signal=${signal}`);
    backendProc = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setTitle('SigmX — backend stopped');
    }
  });
}

// Poll the backend /health endpoint until it responds (or timeout).
function waitForBackend(maxWaitMs = 60000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tryOnce = () => {
      const req = http.get(
        { host: HOST, port: PORT, path: '/health', timeout: 2000 },
        (res) => {
          if (res.statusCode === 200) {
            res.resume();
            resolve();
          } else {
            res.resume();
            retry();
          }
        },
      );
      req.on('error', retry);
      req.on('timeout', () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (Date.now() - start > maxWaitMs) {
        reject(new Error(`backend did not become healthy within ${maxWaitMs}ms`));
        return;
      }
      setTimeout(tryOnce, 500);
    };
    tryOnce();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'SigmX',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Clear the HTTP cache before loading: Electron aggressively caches responses
  // across launches, so a stale text/plain JS response from an earlier broken
  // backend (pre-MIME-fix) would keep producing a white screen even after the
  // server is fixed. This forces a fresh fetch every launch.
  mainWindow.webContents.session.clearCache().catch(() => {});

  mainWindow.loadURL(`http://${HOST}:${PORT}/`);

  // Forward renderer console messages to the main-process stdout so white-screen
  // JS errors are visible in the backend log (not just in DevTools).
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    const tag = ['LOG', 'WARN', 'ERROR'][level] || `L${level}`;
    console.log(`[renderer:${tag}] ${message} (${sourceId}:${line})`);
  });

  // Auto-open DevTools in dev mode so renderer errors are visible (white-screen
  // debugging). Production builds skip this.
  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  // Open external links (http/https) in the system browser, not inside the app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// Ensure a single instance — refuse a second window, focus the existing one.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    spawnBackend();
    try {
      await waitForBackend();
    } catch (err) {
      console.error(`[sigmx] ${err.message}`);
      // Still open the window so the user sees something; backend logs stream to console.
    }
    createWindow();
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}

function killBackend() {
  if (!backendProc) return;
  try {
    if (process.platform === 'win32') {
      // taskkill the whole tree so the uvicorn child dies too.
      spawn('taskkill', ['/pid', String(backendProc.pid), '/f', '/t']);
    } else {
      backendProc.kill('SIGTERM');
    }
  } catch (e) {
    console.error(`[sigmx] failed to kill backend: ${e}`);
  }
}

app.on('before-quit', killBackend);
process.on('exit', killBackend);
process.on('SIGINT', () => { killBackend(); process.exit(0); });
process.on('SIGTERM', () => { killBackend(); process.exit(0); });
