#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热搜摘要 A/B 对照（仅验证，不写 hotlists.json）。

控制组：读取已提交的 hotlists.json 中现有的腾讯反查摘要（不重复烧积分）。
实验组：对同样的热词跑新管线 GNews → DS 压缩 → 腾讯兜底。
输出 ab_report.md（逐词对照）+ 控制台摘要，供决定是否全切 DS。
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_hotlists import fetch_weibo, fetch_toutiao, fetch_baidu
from fetch_news import (gnews_search, google_news, fetch_meta_description,
                        is_low_quality_summary, search_tn_summary, summarize_with_ds)

DS_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
GNEWS_KEY = os.environ.get('GNEWS_API_KEY', '')


def load_cache():
    """已提交 hotlists.json 里的现有摘要（腾讯反查产物）作为控制组"""
    cache = {}
    for cand in (os.path.join(os.getcwd(), 'hotlists.json'), '/tmp/hotlists.json'):
        if not os.path.exists(cand):
            continue
        try:
            d = json.load(open(cand, encoding='utf-8'))
            for pl in d.get('platforms', []):
                for it in pl.get('items', []):
                    w = (it.get('word') or '').strip('#').strip()
                    if w and it.get('summary'):
                        cache.setdefault(w, {'summary': it['summary'],
                                             'src': it.get('sum_src', '')})
        except Exception:
            pass
    return cache


def treatment(w):
    """新管线：GNews 真实片段 → DS 压成一句事实；GNews 无覆盖则 Google/meta → DS；
    都失败才回退腾讯（兜底，计入腾讯消耗）。"""
    material, src = '', ''
    try:
        if GNEWS_KEY:
            gn = gnews_search(w, 1, GNEWS_KEY, 'zh', 'cn')
            if gn:
                material = (gn[0].get('summary') or '').strip()
                src = gn[0].get('source') or 'GNews'
        if not material:
            g = google_news(w, 1)
            if g and not is_low_quality_summary(g[0]['title'], g[0]['summary']):
                material, src = g[0]['summary'], (g[0]['source'] or 'Google')
            elif g:
                d = fetch_meta_description(g[0].get('url'))
                if d:
                    material, src = d, (g[0]['source'] or 'Google-meta')
    except Exception:
        pass
    if material and len(material) >= 8 and DS_KEY:
        ds = summarize_with_ds(w, material, src, DS_KEY)
        if ds:
            return ds, 'DS(' + src + ')'
    if material:
        return material, src
    tn = search_tn_summary(w)
    if tn:
        return tn['summary'], '腾讯'
    return '(无摘要)', '失败'


def main():
    cache = load_cache()
    words = []
    for name, fn in (("微博", fetch_weibo), ("头条", fetch_toutiao), ("百度", fetch_baidu)):
        try:
            p = fn()
            for it in p['items'][:5]:
                w = it['word'].strip('#').strip()
                if w and len(w) >= 2:
                    words.append((name, w))
        except Exception as e:
            print(f"{name} 抓取失败: {e}")

    rows = []
    for name, w in words:
        c = cache.get(w)
        csum = c['summary'] if c else '(缓存无 / 腾讯未覆盖此词)'
        csrc = c['src'] if c else '-'
        t, ts = treatment(w)
        rows.append((name, w, csum, csrc, t, ts))

    for name, w, csum, csrc, t, ts in rows:
        print(f"\n【{name}】{w}")
        print(f"  原({csrc}): {csum}")
        print(f"  新({ts}): {t}")

    md = "# 热搜摘要 A/B 对比（原=腾讯反查 / 新=GNews+DeepSeek）\n\n"
    md += f"- DeepSeek: {'启用' if DS_KEY else '**未配置**'}\n"
    md += f"- GNews: {'启用' if GNEWS_KEY else '**未配置**'}\n\n"
    md += "> 控制组取自已提交的 hotlists.json（腾讯反查产物，不重复消耗积分）；"
    md += "实验组为本次实时 GNews+DS 结果。\n\n"
    cur = None
    for name, w, csum, csrc, t, ts in rows:
        if name != cur:
            md += f"## {name}\n\n"; cur = name
        md += f"**{w}**\n\n- 原管线（{csrc}）：{csum}\n- 新管线（{ts}）：{t}\n\n"
    with open('ab_report.md', 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"\n报告已写 ab_report.md（{len(rows)} 词）")


if __name__ == '__main__':
    main()
