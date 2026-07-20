// crypto-key.js — 轻量密钥加解密（AES-256-GCM）
//
// 设计目的：让 DeepSeek API Key 在磁盘上不以明文 sk-... 形式存在。
// 主进程启动时用 decryptKey() 还原明文并注入后端环境变量，明文只停留在进程内存里。
//
// 安全说明（务必清楚）：
//   桌面端无法做到“绝对不可破解”——派生密钥的素材（PASSPHRASE/SALT）随主进程一起打包进 asar，
//   任何能拿到安装包并解包 asar 的人都能还原出派生密钥、进而解出 key。
//   但本方案保证：(1) 仓库与安装包内不再有任何 sk-... 明文；(2) 磁盘落地的只有密文；
//   (3) 明文不会以文件形式停留在用户数据目录。相比明文存储是实质性提升。
'use strict';

const crypto = require('crypto');

// 派生密钥素材：编译进主进程，不在任何明文文件里暴露 sk-...
// 注意：这不是“密码学机密”，只是把密钥从明文 sk-... 挪进二进制里，提高提取门槛。
const PASSPHRASE = 'daydayup-mgj-v0.3.4-static-secret-9c41e7a2b8f0d3';
// 16 字节盐（hex），与 PASSPHRASE 一起参与 scrypt 派生
const SALT = Buffer.from('d4a373a05a2c5c3a1e0f8b2c6d4e7f90', 'hex');

function _deriveKey() {
  // scrypt：对暴力破解友好，派生出 32 字节（256 位）AES 密钥
  return crypto.scryptSync(PASSPHRASE, SALT, 32);
}

// 加密：输出 "ivB64:tagB64:cipherB64"
function encryptKey(plain) {
  const key = _deriveKey();
  const iv = crypto.randomBytes(12); // GCM 推荐 12 字节 IV
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const enc = Buffer.concat([cipher.update(String(plain), 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag(); // GCM 认证标签，防篡改
  return [
    iv.toString('base64'),
    tag.toString('base64'),
    enc.toString('base64'),
  ].join(':');
}

// 解密：输入 encryptKey 的产物，还原明文；格式不符或受损则抛错
function decryptKey(payload) {
  const raw = String(payload).trim();
  const parts = raw.split(':');
  if (parts.length !== 3) {
    throw new Error('密钥格式不正确（期望 iv:tag:cipher）');
  }
  const iv = Buffer.from(parts[0], 'base64');
  const tag = Buffer.from(parts[1], 'base64');
  const data = Buffer.from(parts[2], 'base64');
  const key = _deriveKey();
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
  decipher.setAuthTag(tag);
  const dec = Buffer.concat([decipher.update(data), decipher.final()]);
  return dec.toString('utf8');
}

// 判断一段内容是否为本模块加密格式（iv:tag:cipher，三段 base64）
function isEncrypted(payload) {
  const parts = String(payload).trim().split(':');
  if (parts.length !== 3) return false;
  try {
    return (
      Buffer.from(parts[0], 'base64').length === 12 &&
      Buffer.from(parts[1], 'base64').length === 16 &&
      Buffer.from(parts[2], 'base64').length > 0
    );
  } catch (_) {
    return false;
  }
}

module.exports = { encryptKey, decryptKey, isEncrypted };
