// preload.js — bridge a minimal API to the renderer.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('lifemgr', {
  version: '0.2.0',
  platform: process.platform,
});
