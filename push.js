// 晨报总览 · Web Push 推送脚本（node 版，云端/本地通用）
// 读订阅列表 + VAPID：优先环境变量 VAPID_JSON / SUBS_JSON（GitHub Actions Secrets），
// 否则回退本地文件 ~/.workbuddy/ai-daily-vapid.json / ai-daily-subs.json
// 推送「今日晨报已更新」通知
const webpush = require('web-push');
const fs = require('fs');
const os = require('os');
const path = require('path');

const HOME = os.homedir();
const VAPID = process.env.VAPID_JSON
  ? JSON.parse(process.env.VAPID_JSON)
  : JSON.parse(fs.readFileSync(path.join(HOME, '.workbuddy', 'ai-daily-vapid.json'), 'utf-8'));
const SUBS_RAW = process.env.SUBS_JSON || (() => {
  const f = path.join(HOME, '.workbuddy', 'ai-daily-subs.json');
  return fs.existsSync(f) ? fs.readFileSync(f, 'utf-8') : null;
})();
const URL = 'https://rayon0727.github.io/ai-daily/';

if (!SUBS_RAW) {
  console.log('no subscription, skip push');
  process.exit(0);
}
let subs = [];
try {
  subs = JSON.parse(SUBS_RAW);
} catch (e) {
  console.log('subs parse error:', String(e.message || e).slice(0, 120));
  process.exit(0);
}
if (!Array.isArray(subs) || !subs.length) {
  console.log('no subscriptions, skip push');
  process.exit(0);
}

webpush.setVapidDetails(VAPID.subject, VAPID.publicKey, VAPID.privateKey);
const payload = JSON.stringify({
  title: process.env.TITLE || 'AI 晨报',
  body: process.env.BODY || '今日晨报已更新，点开查看',
  url: URL,
});

(async () => {
  let ok = 0, fail = 0;
  for (const sub of subs) {
    try {
      await webpush.sendNotification(sub, payload);
      ok++;
    } catch (e) {
      fail++;
      console.log('fail:', String(e.message || e).slice(0, 150));
    }
  }
  console.log(`push done: ${ok} ok, ${fail} fail`);
})();
