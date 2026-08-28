#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨报数据抓取：腾讯 hot（热点榜）+ Google News RSS 搜索（免费，主）→ 失败回退腾讯 CLI search。
输出（与 tencent-news-cli 相同文本格式，供 gen_daily.py parse_tn 解析）:
  <out>/tn_hot.txt  <out>/tn_iot_cn.txt  <out>/tn_iot_global.txt
用法: python3 fetch_news.py [out_dir]   # 默认 /tmp
"""
import html as html_mod
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

BJT = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"


def cli(args, limit):
    """调用 tencent-news-cli，返回原始文本输出；不可用/异常返回 ''"""
    exe = shutil.which('tencent-news-cli')
    if not exe:
        exe = os.path.expanduser('~/.tencent-news-cli/bin/tencent-news-cli')
    if not os.path.exists(exe):
        return ''
    try:
        r = subprocess.run([exe] + args + ['--limit', str(limit)],
                           capture_output=True, text=True, timeout=25)
        return r.stdout or ''
    except Exception:
        return ''


def google_news(q, limit):
    """Google News RSS 搜索（免费无限量，云端境外可达）。
    返回 [{title, summary, source, url, time}]；失败/无结果返回 []"""
    url = ('https://news.google.com/rss/search?q=' + urllib.parse.quote(q) +
           '&hl=zh-CN&gl=CN&ceid=CN:zh')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        xml = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'ignore')
    except Exception:
        return []
    items = []
    for m in re.finditer(r'<item>(.*?)</item>', xml, re.S):
        it = m.group(1)
        t = re.search(r'<title>(.*?)</title>', it, re.S)
        l = re.search(r'<link>(.*?)</link>', it, re.S)
        p = re.search(r'<pubDate>(.*?)</pubDate>', it, re.S)
        d = re.search(r'<description>(.*?)</description>', it, re.S)
        title = html_mod.unescape(re.sub(r'<[^>]+>', '', t.group(1))).strip() if t else ''
        if not title or title in ('无结果', 'No results'):
            continue
        desc_html = d.group(1) if d else ''
        src = ''
        sm = re.search(r'<a[^>]*>([^<]+)</a>', desc_html)
        if sm:
            src = html_mod.unescape(sm.group(1)).strip()
        desc = re.sub(r'<[^>]+>', ' ', desc_html)
        desc = html_mod.unescape(re.sub(r'\s+', ' ', desc)).strip()
        if src and desc.startswith(src):
            desc = desc[len(src):].strip(' &nbsp; ')
        desc = desc[:90]
        time_s = ''
        if p:
            try:
                time_s = parsedate_to_datetime(p.group(1)).astimezone(BJT).strftime('%Y-%m-%d %H:%M')
            except Exception:
                time_s = ''
        items.append({'title': title, 'summary': desc, 'source': src,
                      'url': html_mod.unescape(l.group(1)) if l else '', 'time': time_s})
        if len(items) >= limit:
            break
    return items


def to_cli_text(records):
    """转成 tencent-news-cli 文本格式（gen_daily.py parse_tn 可解析）"""
    out = []
    for i, r in enumerate(records, 1):
        out.append(f"{i}. 标题：{r['title']}")
        if r.get('summary'):
            out.append(f"    摘要：{r['summary']}")
        if r.get('source'):
            out.append(f"    来源：{r['source']}")
        if r.get('time'):
            out.append(f"    发布时间：{r['time']}")
        if r.get('url'):
            out.append(f"    链接：{r['url']}")
        out.append('')
    return '\n'.join(out)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    os.makedirs(out_dir, exist_ok=True)
    results = []

    # 1. 热点新闻：腾讯 hot（1 次/天，便宜，保留）
    hot_txt = cli(['hot'], 10)
    with open(f'{out_dir}/tn_hot.txt', 'w', encoding='utf-8') as f:
        f.write(hot_txt or '')
    results.append(f"hot: {'CLI' if hot_txt else 'EMPTY'}")

    # 2. 物联网搜索：Google News RSS（免费）→ 失败回退腾讯 CLI search
    for name, q in (('cn', '物联网'), ('global', '全球 物联网')):
        recs = google_news(q, 8)
        if recs:
            txt = to_cli_text(recs)
            tag = f'Google({len(recs)})'
        else:
            txt = cli(['search', q], 8)
            tag = 'CLI' if txt else 'EMPTY'
        with open(f'{out_dir}/tn_iot_{name}.txt', 'w', encoding='utf-8') as f:
            f.write(txt or '')
        results.append(f"iot_{name}: {tag}")

    print(' | '.join(results))
    for fn in ('tn_hot.txt', 'tn_iot_cn.txt', 'tn_iot_global.txt'):
        p = os.path.join(out_dir, fn)
        print(f'  {fn}: {os.path.getsize(p)} bytes')


if __name__ == '__main__':
    main()
