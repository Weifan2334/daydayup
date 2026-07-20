// encrypt-key.js — 把明文 DeepSeek Key 加密写入 deepseek.key
//
// 用法：
//   node encrypt-key.js <sk-...>          从参数读取明文 key
//   echo <sk-...> | node encrypt-key.js   从 stdin 读取明文 key
//
// 写入位置：与本脚本同目录的 deepseek.key（加密后内容）。
// 之后重新打包（build:dir / build）即可让桌面端使用新 key。
// 注意：本工具只改「内置默认 key」，不会触碰用户数据目录；要换 key 必须重新打包。
'use strict';

const fs = require('fs');
const path = require('path');
const { encryptKey } = require('./crypto-key');

function readPlain() {
  if (process.argv[2] && process.argv[2].length) {
    return process.argv[2];
  }
  try {
    return fs.readFileSync(0, 'utf8'); // stdin
  } catch (_) {
    return '';
  }
}

const plain = String(readPlain()).trim();
if (!plain) {
  console.error('未提供 key。用法：node encrypt-key.js <sk-...>');
  process.exit(1);
}

const outPath = path.join(__dirname, 'deepseek.key');
fs.writeFileSync(outPath, encryptKey(plain), 'utf8');
console.log('已加密写入：', outPath);
console.log('（该文件内容现为密文，重打包后桌面端会在启动时自动解密注入后端）');
