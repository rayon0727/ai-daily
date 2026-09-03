#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「全网热搜榜」独立页 hot.html（复用晨报设计语言）
输入: /tmp/hotlists.json 输出: MyWork/晨报总览/hot.html + MyWork/ai-daily-site/hot.html
纯静态单文件，无外部资源；暗色模式与主页共享 localStorage key ai-daily-theme。
"""
import json, re, sys

TPL = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#4338ca">
<title>朝闻 · 全网热搜榜 · __DATE__</title>
<style>
  :root{
    --bg:#f4f6fb; --card:#ffffff; --ink:#1c2434; --ink-2:#5b6472; --ink-3:#8a93a3;
    --line:#e6eaf2; --accent:#4f46e5;
  }
  [data-theme="dark"]{
    --bg:#14161f; --card:#1e2130; --ink:#e8eaf2; --ink-2:#a8aebf; --ink-3:#6d7385;
    --line:#2c3040; --accent:#818cf8;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased;transition:background .25s,color .25s}
  .wrap{max-width:920px;margin:0 auto;padding:0 20px}

  /* Hero */
  .hero{background:linear-gradient(135deg,#4338ca 0%,#7c3aed 42%,#be185d 78%,#dc2626 100%);color:#fff;padding:38px 0 26px;position:relative;overflow:hidden}
  .hero::before,.hero::after{content:"";position:absolute;border-radius:50%;background:rgba(255,255,255,.08)}
  .hero::before{width:340px;height:340px;top:-170px;right:-80px}
  .hero::after{width:200px;height:200px;bottom:-100px;right:180px}
  .hero .wrap{position:relative;z-index:1}
  .hero-top{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .hero-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.28);padding:4px 12px;border-radius:999px;font-size:12px;letter-spacing:.08em;margin-bottom:10px}
  .theme-toggle{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:999px;padding:6px 14px;font-size:13px;cursor:pointer;flex-shrink:0;transition:background .15s}
  .theme-toggle:hover{background:rgba(255,255,255,.28)}
  .hero h1{font-size:32px;font-weight:800;letter-spacing:.01em;margin-bottom:6px}
  .hero .date-line{font-size:14px;color:rgba(255,255,255,.88);margin-bottom:16px}
  .hero-stats{display:flex;gap:10px;flex-wrap:wrap}
  .stat{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22);border-radius:12px;padding:8px 14px;min-width:104px;display:flex;flex-direction:column;gap:1px}
  .stat .num{font-size:19px;font-weight:700;line-height:1.2}
  .stat .lbl{font-size:11px;color:rgba(255,255,255,.8)}
  .stat.total{background:rgba(255,255,255,.92);color:#4338ca}
  .stat.total .lbl{color:#6b7280}

  /* Tab 切换条 */
  .tabs{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30}
  .tabs .wrap{display:flex;gap:6px;padding-top:10px;padding-bottom:10px}
  .tab{display:inline-flex;align-items:center;gap:7px;padding:8px 22px;border-radius:999px;font-size:14px;font-weight:700;text-decoration:none;color:var(--ink-2);border:1px solid var(--line);transition:all .16s;background:transparent}
  .tab:hover{border-color:var(--accent);color:var(--accent)}
  .tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}

  main{padding:28px 0 40px}
  .pl{margin-bottom:34px}
  .pl-head{display:flex;align-items:center;gap:10px;border-bottom:2px solid var(--line);padding-bottom:10px;margin-bottom:14px;flex-wrap:wrap}
  .pl-ico{width:34px;height:34px;border-radius:9px;flex-shrink:0;display:block;object-fit:cover}
  .pl-name{font-size:19px;font-weight:800}
  .pl-note{font-size:12px;color:var(--ink-3)}
  .pl-count{font-size:12px;color:var(--ink-3);background:var(--card);border:1px solid var(--line);border-radius:999px;padding:2px 10px;margin-left:auto}

  .hl-list{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--card)}
  .hl-item{display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding:11px 16px;text-decoration:none;transition:background .13s;min-width:0}
  .hl-item:hover{background:var(--chip-bg,#f0f2f8)}
  .hl-item + .hl-item{border-top:1px dashed var(--line)}
  .hl-rank{width:26px;height:26px;border-radius:8px;font-size:13px;font-weight:800;color:#fff;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--chip-bg,#eef0f6);color:var(--ink-3)}
  .hl-rank.r1{background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff}
  .hl-rank.r2{background:linear-gradient(135deg,#94a3b8,#64748b);color:#fff}
  .hl-rank.r3{background:linear-gradient(135deg,#d97706,#b45309);color:#fff}
  .hl-word{flex:1;min-width:0;font-size:14.5px;font-weight:600;color:var(--ink);line-height:1.45;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical}
  .hl-item:hover .hl-word{color:var(--accent)}
  .hl-label{font-size:10.5px;font-weight:800;padding:1px 7px;border-radius:999px;flex-shrink:0}
  .hl-label.b{color:#be123c;background:#ffe4e6}
  .hl-label.h{color:#b45309;background:#fef3c7}
  .hl-label.n{color:#047857;background:#d1fae5}
  .hl-label.f{color:#7c3aed;background:#ede9fe}
  .hl-label.x{color:#0f766e;background:#ccfbf1}
  .hl-label.t{color:#1d4ed8;background:#dbeafe}
  [data-theme="dark"] .hl-label.b{color:#fb7185;background:#3a1d24}
  [data-theme="dark"] .hl-label.h{color:#fbbf24;background:#33291a}
  [data-theme="dark"] .hl-label.n{color:#34d399;background:#13332a}
  [data-theme="dark"] .hl-label.f{color:#c4b5fd;background:#2a2440}
  [data-theme="dark"] .hl-label.x{color:#2dd4bf;background:#12302d}
  [data-theme="dark"] .hl-label.t{color:#93c5fd;background:#16294a}
  .hl-hot{font-size:12px;color:var(--ink-3);flex-shrink:0;white-space:nowrap;display:inline-flex;align-items:center;gap:3px}
  .hl-sum{flex-basis:100%;font-size:12px;color:var(--ink-2);line-height:1.5;min-width:0;
    display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;
    padding-left:38px;margin-top:-4px;border-left:2px solid var(--line,#e6eaf2)}

  .pending{border:1px dashed var(--line);border-radius:14px;padding:22px;text-align:center;color:var(--ink-3);font-size:13px}

  footer{background:var(--card);border-top:1px solid var(--line);padding:24px 0 32px;color:var(--ink-2);font-size:13px}
  .foot-inner{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
  .foot-link{color:var(--accent);text-decoration:none;font-weight:600}
  .foot-link:hover{text-decoration:underline}

  .fab{position:fixed;right:22px;bottom:22px;z-index:40}
  .fab button{width:46px;height:46px;border-radius:50%;border:1px solid var(--line);cursor:pointer;font-size:18px;background:var(--card);color:var(--ink);box-shadow:0 6px 18px rgba(28,36,52,.18);opacity:0;pointer-events:none;transition:opacity .2s}
  .fab button.show{opacity:1;pointer-events:auto}
  .fab button:hover{transform:translateY(-2px)}

  @media (max-width:640px){
    .hero h1{font-size:25px}.hero{padding:30px 0 22px}
    .hl-item{gap:9px;padding:10px 12px}
    .hl-word{font-size:13.5px}
    .stat{min-width:calc(50% - 10px)}
  }
</style>
</head>
<body>

<header class="hero">
  <div class="wrap">
    <div class="hero-top">
      <div>
        <span class="hero-badge">🗞️ 朝闻 · 全网热搜</span>
        <h1>全网热搜榜 · __DATE__</h1>
      </div>
      <button class="theme-toggle" id="themeBtn" title="切换明暗">🌙 夜间</button>
    </div>
    <div class="date-line">微博 + 今日头条官方热榜 · 数据抓取于 __FETCHED_AT__</div>
    <div class="hero-stats" id="heroStats"></div>
  </div>
</header>

<nav class="tabs">
  <div class="wrap">
    <a class="tab" href="index.html">📰 今日朝闻</a>
    <a class="tab active" href="hot.html">🔥 全网热搜</a>
  </div>
</nav>

<main class="wrap" id="main"></main>

<footer>
  <div class="wrap foot-inner">
    <span>共 <b id="footTotal">0</b> 个热词 · 数据源：<b>微博</b> / <b>今日头条</b> 官方热榜（每小时自动更新）</span>
    <a class="foot-link" href="index.html">← 回今日晨报</a>
  </div>
</footer>

<div class="fab"><button id="toTop" title="回到顶部">↑</button></div>

<script>
const DATA = __DATA__;
const STORAGE_KEY = 'ai-daily-theme';

function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function labelCls(l){
  const m = {爆:'b',热:'h',新:'n',沸:'f',荐:'x',议:'t'};
  return m[l] || 'h';
}

// Theme（与主页共享）
function toggleTheme(){
  const dark = document.documentElement.getAttribute('data-theme')==='dark';
  if(dark){ document.documentElement.removeAttribute('data-theme'); localStorage.setItem(STORAGE_KEY,'light'); }
  else { document.documentElement.setAttribute('data-theme','dark'); localStorage.setItem(STORAGE_KEY,'dark'); }
  syncThemeBtn();
}
function syncThemeBtn(){
  const dark = document.documentElement.getAttribute('data-theme')==='dark';
  document.getElementById('themeBtn').textContent = dark ? '☀️ 日间' : '🌙 夜间';
}
(function(){
  if(localStorage.getItem(STORAGE_KEY)==='dark') document.documentElement.setAttribute('data-theme','dark');
  syncThemeBtn();
  document.getElementById('themeBtn').addEventListener('click', toggleTheme);
})();

// Stats
const total = DATA.platforms.reduce((a,p)=>a+p.items.length,0);
document.getElementById('heroStats').innerHTML =
  '<div class="stat total"><span class="num">'+total+'</span><span class="lbl">热词总数</span></div>' +
  DATA.platforms.map(p=>'<div class="stat"><span class="num">'+p.items.length+'</span><span class="lbl">'+esc(p.name)+'</span></div>').join('');

// Platforms
const main = document.getElementById('main');
let html = '';
DATA.platforms.forEach((p)=>{
  html += '<section class="pl">'+
    '<div class="pl-head">'+
      '<img class="pl-ico" src="'+p.icon+'" alt="'+esc(p.name)+'">'+
      '<span class="pl-name">'+esc(p.name)+'</span>'+
      '<span class="pl-note">'+esc(p.note||'')+'</span>'+
      '<span class="pl-count">'+p.items.length+' 条</span>'+
    '</div>';
  if(p.items.length){
    html += '<div class="hl-list">'+
      p.items.map(it=>
        '<a class="hl-item" href="'+esc(it.url)+'" target="_blank" rel="noopener noreferrer">'+
          '<span class="hl-rank'+(it.rank<=3?' r'+it.rank:'')+'">'+it.rank+'</span>'+
          '<span class="hl-word">'+esc(it.word)+'</span>'+
          (it.label? '<span class="hl-label '+labelCls(it.label)+'">'+esc(it.label)+'</span>' : '')+
          (it.hot? '<span class="hl-hot">🔥 '+esc(it.hot)+'</span>' : '')+
          (it.summary? '<span class="hl-sum" title="'+esc(it.summary)+'">📄 '+esc(it.summary)+'</span>' : '')+
        '</a>'
      ).join('')+
    '</div>';
  }else{
    html += '<div class="pending">该平台暂无数据（接口波动自动降级）</div>';
  }
  html += '</section>';
});
main.innerHTML = html;
document.getElementById('footTotal').textContent = total;

// Back to top
const toTop = document.getElementById('toTop');
window.addEventListener('scroll', ()=>{
  toTop.classList.toggle('show', (document.documentElement.scrollTop||document.body.scrollTop) > 400);
});
toTop.addEventListener('click', ()=>window.scrollTo({top:0, behavior:'smooth'}));
</script>
</body>
</html>
'''

DEFAULT_OUTS = ['/Users/rayon/WorkBuddy/MyWork/晨报总览/hot.html',
              '/Users/rayon/WorkBuddy/MyWork/ai-daily-site/hot.html']

def build():
    data = json.load(open('/tmp/hotlists.json', encoding='utf-8'))
    html = TPL.replace('__DATA__', json.dumps(data, ensure_ascii=False))
    html = html.replace('__DATE__', data['date'])
    html = html.replace('__FETCHED_AT__', data['fetchedAt'])
    outs = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_OUTS
    for out in outs:
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        print('written:', out, len(html), 'bytes')

if __name__ == '__main__':
    build()
