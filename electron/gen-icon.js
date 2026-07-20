// gen-icon.js — generate icon.png (32x32) without external deps.
// Brand color: #d4a373 (暖陶土 / 明兰花语).
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

function buildPng(w, h, rgb) {
  const rowLen = w * 3 + 1;
  const raw = Buffer.alloc(rowLen * h);
  for (let y = 0; y < h; y++) {
    raw[y * rowLen] = 0; // PNG filter byte: None
    for (let x = 0; x < w; x++) {
      const o = y * rowLen + 1 + x * 3;
      raw[o] = rgb[0]; raw[o + 1] = rgb[1]; raw[o + 2] = rgb[2];
    }
  }
  const compressed = zlib.deflateSync(raw);

  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    table[i] = c >>> 0;
  }
  const crc32 = (buf) => {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < buf.length; i++) c = (table[(c ^ buf[i]) & 0xFF] ^ (c >>> 8)) >>> 0;
    return c ^ 0xFFFFFFFF;
  };

  const sig = Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length, 0);
    const t = Buffer.from(type, 'ascii');
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([t, data])) >>> 0, 0);
    return Buffer.concat([len, t, data, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', compressed), chunk('IEND', Buffer.alloc(0))]);
}

// Brand color hex → RGB
const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec('#d4a373');
const rgb = [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];

fs.mkdirSync(__dirname, { recursive: true });
fs.writeFileSync(path.join(__dirname, 'icon.png'), buildPng(32, 32, rgb));
fs.writeFileSync(path.join(__dirname, 'icon-256.png'), buildPng(256, 256, rgb));
console.log('[gen-icon] wrote icon.png + icon-256.png');
