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

  /** Listen for update-downloaded events from the main process.
   *  callback receives {version, releaseNotes, releaseDate}. */
  onUpdateDownloaded: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on('update-downloaded', handler);
    // Return an unsubscribe function.
    return () => ipcRenderer.removeListener('update-downloaded', handler);
  },

  // ---- Future native features ----
  // openDataDir, showInFolder, etc. go here.
});
