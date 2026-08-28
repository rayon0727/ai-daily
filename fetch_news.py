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


def is_low_quality_summary(title, summary):
    """判断 Google News RSS 的 description 是否无效（与标题重复/过短/仅拼接来源）。

    Google News 常把 description 设成「标题 + 来源」拼接（如「云汉芯城…新方案- B2B 亿邦动力网」），
    与标题高度重合，没有实质信息，需要识别出来并用腾讯 CLI 反查替换。"""
    if not summary or len(summary) < 15:
        return True
    strip = lambda s: re.sub(r'[\s\-—–|｜·,，。、．（）()\[\]【】"\'：:；;]', '', s)
    t = strip(title)
    s = strip(summary)
    if not t:
        return False
    # 摘要完整包含标题 → 纯重复
    if t in s:
        return True
    # 标题较长且摘要以标题主体开头 → 基本是「标题 + 来源」拼接
    if len(t) >= 12 and s.startswith(t[: len(t) // 2 + 6]):
        return True
    return False


def search_tn_summary(title):
    """用腾讯新闻 CLI search 反查标题，取第一条的摘要/来源。

    仅在 Google News 摘要质量差时调用，腾讯 CLI 不可用则返回 None（降级保留原摘要）。"""
    exe = shutil.which('tencent-news-cli')
    if not exe:
        exe = os.path.expanduser('~/.tencent-news-cli/bin/tencent-news-cli')
    if not os.path.exists(exe):
        return None
    try:
        r = subprocess.run([exe, 'search', title, '--limit', '1'],
                           capture_output=True, text=True, timeout=20)
        out = r.stdout or ''
    except Exception:
        return None
    if not out:
        return None
    s = re.search(r'^\s*\d+\.\s*标题[：:]\s*(.*)$', out, re.M)
    if not s:
        return None
    sm = re.search(r'^[ \t]*摘要[:：]\s*(.*)$', out, re.M)
    src = re.search(r'^[ \t]*来源[:：]\s*(.*)$', out, re.M)
    summary = re.sub(r'\s+', ' ', sm.group(1)).strip() if sm else ''
    if not summary or is_low_quality_summary(title, summary):
        return None
    return {'summary': summary[:90], 'source': src.group(1).strip() if src else ''}


def fetch_meta_description(url):
    """抓取新闻原网页的 meta description（免费兜底，不依赖腾讯 CLI 积分）。

    跟随 Google News 重定向到真实 URL；提取 og:description / meta description。
    失败或内容过短返回 None（静默降级，保留原标题）。"""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(400000).decode('utf-8', 'ignore')
            final = r.geturl()
        # 若重定向后仍是 Google News 页面（JS 跳转），meta 不可信 → 放弃
        if 'news.google.com' in final and 'news.google.com' in url:
            return None
        m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', raw, re.I | re.S)
        if not m:
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', raw, re.I | re.S)
        if not m:
            m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', raw, re.I | re.S)
        if not m:
            return None
        desc = html_mod.unescape(m.group(1)).strip()
        desc = re.sub(r'\s+', ' ', desc)
        if len(desc) < 20:
            return None
        return desc[:140]
    except Exception:
        return None


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
        # 媒体名：Google News RSS 有独立 <source url="...">媒体名</source> 子元素
        s = re.search(r'<source[^>]*url="[^"]*"[^>]*>(.*?)</source>', it, re.S)
        title = re.sub(r'<[^>]+>', '', html_mod.unescape(t.group(1))).strip() if t else ''
        if not title or title in ('无结果', 'No results'):
            continue
        src = html_mod.unescape(s.group(1)).strip() if s else ''
        desc_html = html_mod.unescape(d.group(1)) if d else ''
        desc = re.sub(r'<[^>]+>', ' ', desc_html)
        desc = html_mod.unescape(re.sub(r'\s+', ' ', desc)).strip()
        desc = re.sub(r'^[\s\xa0]+', '', desc)[:90]
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
        enriched = 0
        if recs:
            # 摘要质检：Google News 的 description 常与标题重复，质量差则
            # ① 腾讯 CLI 反查（有积分时最佳）→ ② 网页 meta description 兜底（免费）→ ③ 保留原标题
            for r in recs:
                if is_low_quality_summary(r['title'], r['summary']):
                    better = search_tn_summary(r['title'])
                    if not better:
                        md = fetch_meta_description(r.get('url'))
                        if md:
                            better = {'summary': md, 'source': r['source']}
                    if better:
                        r['summary'] = better['summary']
                        if better.get('source'):
                            r['source'] = better['source']
                        enriched += 1
            txt = to_cli_text(recs)
            tag = f'Google({len(recs)},enriched {enriched})' if enriched else f'Google({len(recs)})'
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
