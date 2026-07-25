// SigmX desktop preload — exposes a safe IPC bridge to the renderer.
//
// The renderer is the existing React app served by the Python backend at
// http://localhost:8899. contextIsolation is on, nodeIntegration off.
// This file only exposes a tiny safe bridge via contextBridge.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('sigmxDesktop', {
  isDesktop: true,

  // ---- Auto-update ----

  /** Trigger a manual update check. Returns {ok, version?} */
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),

  /** Quit the app and install the downloaded update. */
  quitAndInstall: () => ipcRenderer.invoke('quit-and-install'),

  /** Listen for update events from the main process. Each returns an unsubscribe fn. */

  // "检查到新版本，正在下载" — {version, releaseNotes, releaseDate}
  onUpdateAvailable: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on('update-available', handler);
    return () => ipcRenderer.removeListener('update-available', handler);
  },

  // "已是最新版本" — {version}
  onUpdateNotAvailable: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on('update-not-available', handler);
    return () => ipcRenderer.removeListener('update-not-available', handler);
  },

  // 下载进度 — {percent, transferred, total, bytesPerSecond}
  onUpdateProgress: (callback) => {
    const handler = (_event, progress) => callback(progress);
    ipcRenderer.on('update-progress', handler);
    return () => ipcRenderer.removeListener('update-progress', handler);
  },

  // 下载完成，下次启动安装 — {version, releaseNotes, releaseDate}
  onUpdateDownloaded: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on('update-downloaded', handler);
    return () => ipcRenderer.removeListener('update-downloaded', handler);
  },

  // 更新失败 — {message}
  onUpdateError: (callback) => {
    const handler = (_event, err) => callback(err);
    ipcRenderer.on('update-error', handler);
    return () => ipcRenderer.removeListener('update-error', handler);
  },
});
