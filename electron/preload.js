// preload.js — bridge a minimal API to the renderer.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('lifemgr', {
  version: '0.3.4',
  platform: process.platform,
});
