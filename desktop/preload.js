// Minimal preload. The renderer is the existing React app served by the Python
// backend at http://localhost:8899 — it behaves exactly as in a browser.
// contextIsolation is on, nodeIntegration off; this file only exposes a tiny
// safe bridge for future native features (window controls, tray, native paths).
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('sigmxDesktop', {
  isDesktop: true,
  // Add native IPC bridges here as needed (e.g. open data dir, show in folder).
});
