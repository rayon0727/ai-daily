#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨报生成脚本（云端/本地通用）v1
数据文件（默认 /tmp，可用 --data-dir 覆盖）：
  tn_hot.txt / tn_iot_cn.txt / tn_iot_global.txt  腾讯新闻 CLI 输出
  aihot_daily_latest.json                          AIHOT 日报
  wechat_media.json                                关注公众号（fetch_wechat_media.py 输出）
模板：当前目录或 --template 指定 ai-daily-template.html（__DATE__/__FETCHED_AT__/__DATA__ 占位）
输出：ai-daily-combined-YYYY-MM-DD.html + index.html（当前目录或 --out-dir）
用法示例：
  python3 gen_daily.py --data-dir /tmp --template ai-daily-template.html
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))
IOT_KEYWORDS = ['物联网','卫星','芯片','5G','6G','蜂窝','模组','eSIM','eUICC','算力','运营商',
                '低轨','半导体','工信部','行动方案','产业创新','智连']
# 国外板块（全球 IoT/AI 专题）专属过滤词：摘要须含其一才算"相关业务动态"，
# 用来挡掉腾讯 CLI 偶发的串文（骑电动车戴头盔 / 秦皇岛观光等无关正文）。
FOREIGN_KW = ['物联网','卫星','低轨','星座','芯片','半导体','5G','6G','蜂窝','模组','eSIM',
              '算力','运营商','边缘','AI','人工智能','机器人','自动驾驶','云','大模型',
              '新能源','电池','航天','通信','智能','传感','雷达','无人机','数字孪生']
TOPICS = [
    ('🛰️ 卫星与低轨', ['卫星','低轨','星座','航天','太空','吉利']),
    ('🔌 芯片与模组', ['芯片','半导体','蜂窝','模组','eSIM','eUICC']),
    ('📡 5G·6G 与网络', ['5G','6G','通信','算力','网络','智连','工业互联网']),
    ('🏛️ 政策与产业', ['政策','行动方案','工信部','产业','规划','商用试验','批复']),
]
AUTHORITY = ['央视新闻','人民网','新华社','环球','工信部','第一财经','澎湃新闻','中国新闻周刊']
AIHOT_COLORS = ['#6366f1','#0ea5e9','#d97706','#0d9488','#db2777']
WM_COLORS = ['#ea580c', '#0891b2']

def parse_tn(path):
    records, cur = [], None
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            m = re.match(r'^(\d+)\.\s*标题[：:]\s*(.*)$', line)
            if m:
                if cur: records.append(cur)
                cur = {'title': m.group(2).strip(), 'summary': '', 'source': '', 'time_raw': '', 'url': ''}
            elif cur is not None:
                if re.match(r'^摘要[:：]', line): cur['summary'] = re.sub(r'^摘要[:：]\s*', '', line)
                elif re.match(r'^来源[:：]', line): cur['source'] = re.sub(r'^来源[:：]\s*', '', line)
                elif re.match(r'^发布时间[:：]', line): cur['time_raw'] = re.sub(r'^发布时间[:：]\s*', '', line)
                elif re.match(r'^链接[:：]', line): cur['url'] = re.sub(r'^链接[:：]\s*', '', line)
                elif cur['summary'] and '链接' not in line and '标题' not in line: cur['summary'] += line
    if cur: records.append(cur)
    return records

def ts_from(t):
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})', (t or '').strip())
    if not m: return None
    y, mo, d, h, mi = map(int, m.groups())
    return int(datetime(y, mo, d, h, mi, tzinfo=BJT).timestamp())

def fmt_time(t):
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})', (t or '').strip())
    if not m: return (t or '').strip()
    y, mo, d, h, mi = map(int, m.groups())
    return f'{mo}月{d}日 {h:02d}:{mi:02d}' if y == NOW.year else f'{y}年{mo}月{d}日 {h:02d}:{mi:02d}'

def is_iot(t): return any(k in t for k in IOT_KEYWORDS)
def topic_of(t):
    for name, kws in TOPICS:
        if any(k in t for k in kws): return name
    return None
def reason_of(title, full, src, tag, topic):
    parts = []
    if '相关' in tag and topic: parts.append(topic.replace(' ', '') + '领域动态')
    if '热点' in tag: parts.append('当日热点')
    if any(a in src for a in AUTHORITY): parts.append('权威来源')
    if not parts: parts.append('行业快讯')
    return '、'.join(parts[:2])
def score(title, summary, src, ts, is_hot):
    s = 0; blob = title + summary
    if is_iot(title): s += 3
    elif is_iot(blob): s += 2
    if ts:
        age = (NOW.timestamp() - ts) / 86400
        if age <= 2: s += 2
        elif age <= 7: s += 1
    if any(a in src for a in AUTHORITY): s += 1
    if is_hot: s += 1
    return s

def _has_cjk(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s or ''))
def _cjk_chars(s):
    return re.findall(r'[\u4e00-\u9fff]', s or '')
def is_domestic_mismatch(title, full):
    """串文防护：标题与正文零共享汉字（腾讯 CLI 偶发返回错配文章正文）。
    仅在高度确信时返回 True——正常新闻标题与正文至少共享一个汉字，
    零共享几乎必然是不同文章的正文被错配进来；清空正文仅留标题。"""
    f = (full or '').strip()
    if len(f) < 30:
        return False
    tc, fc = _cjk_chars(title), _cjk_chars(f[:140])
    return len(tc) >= 3 and len(fc) >= 8 and len(set(tc) & set(fc)) == 0

def main():
    global NOW
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default='', help='YYYY-MM-DD，默认今天')
    ap.add_argument('--data-dir', default='/tmp')
    ap.add_argument('--template', default='ai-daily-template.html')
    ap.add_argument('--out-dir', default='.')
    args = ap.parse_args()

    if args.date:
        y, mo, d = map(int, args.date.split('-'))
        NOW = datetime(y, mo, d, 9, 35, tzinfo=BJT)
    else:
        NOW = datetime.now(BJT)

    D = args.data_dir
    # ---------- 腾讯 ----------
    tn_files = [('热点新闻', f'{D}/tn_hot.txt', '#e11d48'),
                ('国内物联网', f'{D}/tn_iot_cn.txt', '#0ea5e9'),
                ('国外·全球物联网', f'{D}/tn_iot_global.txt', '#0d9488')]
    secs_tn = []
    mismatch_count = 0
    foreign_kept = 0
    for label, path, color in tn_files:
        items = []
        for r in parse_tn(path):
            ts = ts_from(r['time_raw'])
            full = re.sub(r'\s+', ' ', r['summary']).strip()
            # 串文防护：腾讯 CLI 偶发返回错配正文（标题与正文零共享汉字），清空正文仅留标题
            if is_domestic_mismatch(r['title'], full):
                full = ''
                mismatch_count += 1
            # 国外板块：仅保留"有中文可读摘要 + 属 IoT/AI 专题"的条目——
            # 用户无法打开外链，纯英文/无中文摘要=噪声；串文（骑电动车戴头盔/秦皇岛观光等）
            # 因不含任何 IoT 关键词也会被滤掉。双重条件避免保留垃圾。
            if label == '国外·全球物联网':
                blob = r['title'] + full
                if len(_cjk_chars(full)) < 10 or not any(k in blob for k in FOREIGN_KW):
                    continue
                foreign_kept += 1
            is_hot = (label == '热点新闻')
            tag = '⚡ 相关' if is_iot(r['title'] + full) else ('🔥 热点' if is_hot else '')
            topic = topic_of(r['title'] + full)
            items.append({'title': r['title'], 'full': full, 'source': r['source'],
                          'time': fmt_time(r['time_raw']), 'ts': ts, 'url': r['url'],
                          'tag': tag, 'topic': topic,
                          'reason': reason_of(r['title'], full, r['source'], tag, topic),
                          'score': score(r['title'], full, r['source'], ts, is_hot)})
        items.sort(key=lambda x: (x['ts'] is None, -(x['ts'] or 0)))
        if items:
            secs_tn.append({'label': label, 'color': color, 'items': items})

    # ---------- AIHOT ----------
    aihot = json.load(open(f'{D}/aihot_daily_latest.json', encoding='utf-8'))
    rep = aihot['report']
    secs_ai = []
    for i, s in enumerate(rep['sections']):
        items = []
        for it in s['items']:
            full = re.sub(r'\s+', ' ', it.get('summary') or '').strip()
            title = it.get('title', ''); src = (it.get('source') or {}).get('name', '')
            tag = '⚡ 相关' if is_iot(title + full) else ''
            topic = topic_of(title + full)
            items.append({'title': title, 'full': full, 'source': src, 'time': '', 'ts': None,
                          'url': it.get('links', {}).get('original') or it.get('links', {}).get('aihot', ''),
                          'tag': tag, 'topic': topic,
                          'reason': reason_of(title, full, src, tag, topic),
                          'score': score(title, full, src, None, False)})
        secs_ai.append({'label': s['label'], 'color': AIHOT_COLORS[i], 'items': items})

    parts = [
        {'key': 'tn', 'title': '腾讯新闻资讯推送', 'desc': '国内热点 + 物联网行业资讯（每日 09:30 定时）',
         'sourceName': '腾讯新闻', 'sourceUrl': 'https://view.inews.qq.com', 'sections': secs_tn},
        {'key': 'aihot', 'title': 'AI HOT 精选日报', 'desc': 'AI 行业技术前沿（模型 / 产品 / 论文，可选读）',
         'sourceName': 'AIHOT', 'sourceUrl': rep.get('links', {}).get('aihot', ''), 'sections': secs_ai},
    ]

    # ---------- 公众号 ----------
    seq = 0
    ALL = []
    for p in parts:
        for s in p['sections']:
            for it in s['items']:
                seq += 1
                it['n'] = seq
                it['old'] = bool(it['ts']) and (NOW.timestamp() - it['ts']) / 86400 > 30
                ALL.append(it)
    try:
        wm = json.load(open(f'{D}/wechat_media.json', encoding='utf-8'))
        wm_sections = []
        for i, src in enumerate(wm.get('sources', [])):
            items = []
            for it in src.get('items', []):
                seq += 1
                items.append({'n': seq, 'title': it['title'], 'full': '', 'source': src['name'],
                              'time': '', 'ts': None, 'url': it['url'], 'tag': '', 'topic': None,
                              'reason': '', 'score': 0, 'old': False})
            wm_sections.append({'label': src['name'], 'color': WM_COLORS[i % 2], 'items': items})
        parts.append({'key': 'wm', 'title': '关注公众号', 'desc': '垂直号最新文章 · 点标题直达原文',
                      'sourceName': '', 'sourceUrl': '', 'sections': wm_sections})
    except FileNotFoundError:
        print('wechat_media.json 缺失，跳过公众号部分')

    # ---------- highlights / hotwords / topics ----------
    cand = [it for it in ALL if not it['old']]
    cand.sort(key=lambda x: (-x['score'], -(x['ts'] or 0)))
    highlights = [{'n': it['n'], 'title': it['title'], 'source': it['source'], 'tag': it['tag'],
                   'time': it['time'], 'reason': it['reason']} for it in cand[:5]]

    cnt = Counter()
    for it in ALL:
        if it['old']: continue
        blob = it['title'] + ' ' + it['full']
        for kw in IOT_KEYWORDS:
            c = blob.count(kw)
            if c > 0: cnt[kw] += c
    hotwords = [{'w': w, 'c': c} for w, c in cnt.most_common(8)]

    topic_items = {}
    for it in ALL:
        if '相关' in it['tag'] and not it['old'] and it['topic']:
            topic_items.setdefault(it['topic'], []).append(
                {'n': it['n'], 'title': it['title'], 'source': it['source'], 'time': it['time'], 'url': it['url']})
    topics = sorted([{'name': k, 'items': v} for k, v in topic_items.items()], key=lambda t: -len(t['items']))

    weekday = '一二三四五六日'[NOW.weekday()]
    DATA = {'date': f'{NOW.year}年{NOW.month}月{NOW.day}日 星期{weekday}', 'parts': parts, 'total': seq,
            'fetchedAt': f'{NOW.year}年{NOW.month}月{NOW.day}日 {NOW.strftime("%H:%M")}（北京时间）',
            'highlights': highlights, 'hotwords': hotwords, 'topics': topics}
    print(f'total: {seq} | 相关: {sum(1 for it in ALL if "相关" in it["tag"])} | 往期: {sum(1 for it in ALL if it["old"])} | 串文清空: {mismatch_count} | 国外保留: {foreign_kept}条')

    # ---------- 生成 ----------
    tpl = open(args.template, encoding='utf-8').read()
    html = tpl.replace('__DATE__', DATA['date'])
    html = html.replace('__FETCHED_AT__', DATA['fetchedAt'])
    html = html.replace('__DATA__', json.dumps(DATA, ensure_ascii=False))

    ymd = NOW.strftime('%Y-%m-%d')
    out1 = f'{args.out_dir}/ai-daily-combined-{ymd}.html'
    out2 = f'{args.out_dir}/index.html'
    with open(out1, 'w', encoding='utf-8') as f:
        f.write(html)
    with open(out2, 'w', encoding='utf-8') as f:
        f.write(html)
    print('written:', out1, len(html), 'bytes')
    print('written:', out2, len(html), 'bytes')

    js = re.search(r'<script>(.*?)</script>', html, re.S).group(1)
    open('/tmp/gen_daily_check.js', 'w', encoding='utf-8').write(js)

if __name__ == '__main__':
    NOW = None
    main()
