#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
晨报总览 · 归档索引重建脚本
扫描 晨报总览/ 目录下所有 ai-daily-combined-YYYY-MM-DD.html，
重建 archive.html（历史列表，按日期倒序，最新在前）。
不包含 index.html（当日入口副本）与 archive.html 自身。
"""
import os
import re
import sys
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    files = sorted(
        [f for f in os.listdir(DIR)
         if re.match(r'^ai-daily-combined-\d{4}-\d{2}-\d{2}\.html$', f)],
        reverse=True,
    )
    if not files:
        print('no daily files found')
        return

    cards = ''
    for i, f in enumerate(files):
        m = re.match(r'^ai-daily-combined-(\d{4}-\d{2}-\d{2})\.html$', f)
        date = m.group(1)
        dt = datetime.strptime(date, '%Y-%m-%d')
        label = f'{dt.year}年{dt.month}月{dt.day}日 星期{"一二三四五六日"[dt.weekday()]}'
        cards += f'''
    <a class="item" href="{f}">
      <span class="no">{i + 1:02d}</span>
      <div class="info">
        <span class="date">{label}</span>
        <span class="file">{f}</span>
      </div>
      <span class="go">查看 →</span>
    </a>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 晨报总览 · 往期回顾</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#f4f6fb;color:#1c2434;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.6}}
  .wrap{{max-width:760px;margin:0 auto;padding:48px 20px 60px}}
  .back{{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:#4f46e5;
    text-decoration:none;margin-bottom:20px;border:1px solid #e6eaf2;background:#fff;border-radius:999px;padding:5px 14px}}
  .back:hover{{border-color:#4f46e5}}
  h1{{font-size:26px;font-weight:800;margin-bottom:6px}}
  .sub{{color:#5b6472;font-size:14px;margin-bottom:28px}}
  .list{{display:flex;flex-direction:column;gap:12px}}
  .item{{display:flex;align-items:center;gap:16px;background:#fff;border:1px solid #e6eaf2;border-radius:14px;
    padding:16px 18px;text-decoration:none;color:inherit;transition:transform .15s,box-shadow .15s}}
  .item:hover{{transform:translateY(-2px);box-shadow:0 8px 20px rgba(28,36,52,.08)}}
  .no{{font-size:13px;font-weight:800;color:#fff;background:#4f46e5;border-radius:8px;padding:4px 10px;flex-shrink:0}}
  .info{{display:flex;flex-direction:column;gap:2px;flex:1;min-width:0}}
  .date{{font-size:16px;font-weight:700}}
  .file{{font-size:12px;color:#8a93a3;word-break:break-all}}
  .go{{font-size:13px;font-weight:600;color:#4f46e5;flex-shrink:0}}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="index.html">← 回到今日晨报</a>
  <h1>🗞️ AI 晨报总览 · 往期回顾</h1>
  <div class="sub">每天 09:30 自动生成 · 共 {len(files)} 期</div>
  <div class="list">{cards}</div>
</div>
</body>
</html>'''

    out = os.path.join(DIR, 'archive.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'archive.html rebuilt: {len(files)} entries')

if __name__ == '__main__':
    main()
