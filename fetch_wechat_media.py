#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关注公众号抓取：物联网智库（iot101.com 官网）、物联网头条君（与非网专栏）
输出 JSON 到 /tmp/wechat_media.json：{sources: [{name, desc, items: [{title, url}]}]}
供晨报总览「关注公众号」版块使用。
"""
import html as html_mod
import json
import re
import urllib.request

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'}
ACTIVITY_KW = ('观展', '年会', '峰会', '论坛', '大会', '发布会', '注册', '招商', '议程', '报名', '邀请函', 'CSDI', '奖')


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='ignore')


def clean_title(t):
    t = html_mod.unescape(t).replace('\u3000', ' ').replace('\t', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    # 截掉「｜」副标题/栏目分隔
    t = re.split(r'[｜|]', t)[0].strip()
    return t


def is_activity(title):
    return any(k in title for k in ACTIVITY_KW)


def fetch_iot101(limit=6):
    """物联网智库官网首页文章列表"""
    html = fetch('http://www.iot101.com')
    items, seen = [], set()
    for m in re.finditer(r'href="(https?://www\.iot101\.com/(?:news|guangao)/\d+\.html)"[^>]*>([^<]{8,60})</a>', html):
        url, title = m.group(1), clean_title(m.group(2))
        if not title or title in seen or is_activity(title):
            continue
        seen.add(title)
        items.append({'title': title, 'url': url})
        if len(items) >= limit:
            break
    return items


def fetch_eefocus(limit=6):
    """物联网头条君（与非网专栏）"""
    try:
        html = fetch('https://m.eefocus.com/column/iot101%E5%90%9B')
    except Exception:
        return []
    items, seen = [], set()
    for m in re.finditer(r'href="(https://www\.eefocus\.com/article/\d+\.html)"[^>]*>([^<]{8,60})</a>', html):
        url, title = m.group(1), clean_title(m.group(2))
        if not title or title in seen or is_activity(title):
            continue
        seen.add(title)
        items.append({'title': title, 'url': url})
        if len(items) >= limit:
            break
    return items


def main():
    out = []
    iot101 = fetch_iot101()
    if iot101:
        out.append({'name': '物联网智库', 'desc': 'AIoT 智联网产业媒体', 'items': iot101})
    eefocus = fetch_eefocus()
    if eefocus:
        out.append({'name': '物联网头条君', 'desc': '智次方旗下 · 与非网专栏', 'items': eefocus})
    json.dump({'sources': out}, open('/tmp/wechat_media.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for s in out:
        print(f"== {s['name']} ({len(s['items'])} 条) ==")
        for it in s['items']:
            print('  -', it['title'][:48])


if __name__ == '__main__':
    main()
