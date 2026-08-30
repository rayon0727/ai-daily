#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全网热搜抓取：微博 + 今日头条 Top10（每日快照）
输出: /tmp/hotlists.json  {date, fetchedAt, platforms:[{key,name,color,icon,note,items:[{rank,word,hot,label,url}]}]}
失败平台自动降级（items=[] 或跳过），不中断。
抖音：官方接口需签名、第三方聚合当前网络不可达 → 暂不接入（留 key 占位，后续补）。
"""
import json, re, sys, os, shutil, subprocess, urllib.request
from fetch_news import (google_news, is_low_quality_summary,
                        fetch_meta_description, gnews_search,
                        summarize_with_ds)  # 免费搜索源 + 摘要质检 + 网页兜底 + GNews + DS

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
TIMEOUT = 12
TOP_N = 10
CACHE_HOURS = 24  # 摘要缓存有效期：24 小时内同一热词不重复搜索

def load_summary_cache():
    """从上次结果（仓库 ./hotlists.json 或 /tmp/hotlists.json）读取 word -> 摘要缓存
    过滤掉缓存里的脏数据（src 异常长、或 sum_src 含摘要关键词 → 视为不可信丢弃）"""
    cache = {}
    for cand in (os.path.join(os.getcwd(), "hotlists.json"), "/tmp/hotlists.json"):
        if not os.path.exists(cand):
            continue
        try:
            old = json.load(open(cand, encoding="utf-8"))
            for pl in old.get("platforms", []):
                for it in pl.get("items", []):
                    w = (it.get("word") or "").strip("#").strip()
                    src = it.get("sum_src") or ""
                    summary = it.get("summary") or ""
                    if not w or not summary or "<" in summary:
                        continue
                    # 过滤脏 src：媒体名不会太长，超长说明存的是摘要/URL 片段而非来源
                    if len(src) > 12:
                        continue
                    # 通用质检：缓存里若存的是「热词+来源」拼接的废话摘要，
                    # 视为无效丢弃，强制本轮重新反查（替代原先按关键词的硬编码黑名单）
                    if is_low_quality_summary(w, summary):
                        continue
                    cache[w] = {"summary": summary, "source": src,
                                "ts": it.get("sum_ts") or 0}
            break
        except Exception:
            continue
    return cache

def fetch(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "ignore")

def fmt_hot(v):
    """热度值格式化：14042042 → 1404万；42892251 → 4289万；938 → 938"""
    try:
        n = int(float(v))
    except Exception:
        return str(v)
    if n >= 100000000:
        return f"{n/100000000:.1f}亿"
    if n >= 10000:
        return f"{n/10000:.0f}万"
    return str(n)

def fetch_weibo():
    raw = fetch("https://weibo.com/ajax/side/hotSearch", referer="https://weibo.com/")
    d = json.loads(raw)
    rt = d.get("data", {}).get("realtime", [])
    items = []
    for i, it in enumerate(rt[:TOP_N], 1):
        word = (it.get("word") or "").strip()
        if not word:
            continue
        items.append({
            "rank": i,
            "word": word,
            "hot": fmt_hot(it.get("num")),
            "label": it.get("label_name") or "",
            "url": f"https://s.weibo.com/weibo?q={urllib.parse.quote(word)}",
        })
    return {"key": "weibo", "name": "微博热搜", "color": "#e6162d", "icon": "icon-weibo.png",
            "note": "点击热词查看微博话题讨论", "items": items}

def fetch_toutiao():
    raw = fetch("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    d = json.loads(raw)
    data = d.get("data", [])
    items = []
    for i, it in enumerate(data[:TOP_N], 1):
        title = (it.get("Title") or "").strip()
        if not title:
            continue
        items.append({
            "rank": i,
            "word": title,
            "hot": fmt_hot(it.get("HotValue")),
            "label": "热",
            "url": it.get("Url") or f"https://so.toutiao.com/search?keyword={urllib.parse.quote(title)}",
        })
    return {"key": "toutiao", "name": "今日头条", "color": "#f02c2c", "icon": "icon-toutiao.png",
            "note": "点击热词直达原文 / 话题页", "items": items}

def fetch_baidu():
    """百度热搜（免费匿名 JSON，top.baidu.com）：51 条，取 Top10。无热度值/标签"""
    raw = fetch("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    d = json.loads(raw)
    items_raw = d["data"]["cards"][0]["content"][0]["content"]
    items = []
    for i, it in enumerate(items_raw[:TOP_N], 1):
        word = (it.get("word") or "").strip()
        if not word:
            continue
        items.append({
            "rank": i,
            "word": word,
            "hot": "",
            "label": "",
            "url": it.get("url") or f"https://www.baidu.com/s?wd={urllib.parse.quote(word)}",
        })
    return {"key": "baidu", "name": "百度热搜", "color": "#2932e1", "icon": "icon-baidu.png",
            "note": "点击热词查看百度讨论", "items": items}


def resolve_cli():
    p = shutil.which('tencent-news-cli')
    if p:
        return p
    alt = os.path.expanduser('~/.tencent-news-cli/bin/tencent-news-cli')
    return alt if os.path.exists(alt) else None

def search_tn_summary(word):
    """热词反查腾讯新闻：返回第一条的摘要（摘要/来源），失败或无语义返回 None"""
    cli = resolve_cli()
    if not cli:
        return None
    try:
        out = subprocess.run([cli, 'search', word, '--limit', '1'],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return None
    if not out:
        return None
    m = re.search(r'^\s*\d+\.\s*标题[：:]\s*(.*)$', out, re.M)
    if not m:
        return None
    title = m.group(1).strip()
    s = re.search(r'^[ \t]*摘要[:：]\s*(.*)$', out, re.M)
    src = re.search(r'^[ \t]*来源[:：]\s*(.*)$', out, re.M)
    summary = re.sub(r'\s+', ' ', s.group(1)).strip() if s else ''
    if not summary or len(summary) < 8:
        return None
    return {'title': title, 'summary': summary[:90],
            'source': src.group(1).strip() if src else ''}

def main():
    platforms = []
    results = []
    for name, fn in (("微博", fetch_weibo), ("头条", fetch_toutiao), ("百度", fetch_baidu)):
        try:
            p = fn()
            platforms.append(p)
            results.append(f"{name} OK ({len(p['items'])} 条)")
        except Exception as e:
            results.append(f"{name} FAIL ({type(e).__name__}: {str(e)[:80]})")

    # 热词反查摘要（方案 A：智能增量 + 多源）：每平台 Top5 全局去重；
    # 主源 Google News RSS（免费）→ 失败回退腾讯 search（有积分时）；24h 内命中缓存直接复用。
    # 由 ENRICH_SUMMARIES=1 开启（云端每班执行）。
    from datetime import datetime, timezone, timedelta
    bjt = timezone(timedelta(hours=8))
    now = datetime.now(bjt)
    now_ts = int(now.timestamp())

    enrich = os.environ.get('ENRICH_SUMMARIES', '0') == '1'
    use_ds = os.environ.get('SUMMARIZE_DS', '0') == '1'
    gnews_key = os.environ.get('GNEWS_API_KEY', '')
    cache = load_summary_cache() if enrich else {}
    seen = {}
    reused = enriched = failed = 0
    src_google = src_tn = src_lowq = src_meta = src_ds = src_gnews = 0
    if enrich:
        for p in platforms:
            for it in p['items'][:5]:
                w = it['word'].strip('#').strip()
                if len(w) < 2:
                    continue
                if w in seen:
                    if seen[w]:
                        it['summary'] = seen[w]['summary']
                        it['sum_src'] = seen[w]['source']
                        it['sum_ts'] = seen[w]['ts']
                    continue
                cached = cache.get(w)
                if cached and (now_ts - cached['ts']) < CACHE_HOURS * 3600:
                    it['summary'] = cached['summary']
                    it['sum_src'] = cached['source']
                    it['sum_ts'] = cached['ts']
                    seen[w] = cached
                    reused += 1
                    continue
                r = None
                material = ''
                try:
                    if use_ds and gnews_key:
                        # 新管线：GNews 免费检索真实摘要+直链 → DS 压缩（省腾讯积分）
                        gn = gnews_search(w, 1, gnews_key, 'zh', 'cn')
                        if gn:
                            art = gn[0]
                            material = (art.get('summary') or '').strip()
                            r = {'title': art.get('title', w),
                                 'summary': material or w,
                                 'source': art.get('source') or 'GNews',
                                 'url': art.get('url', '')}
                            src_gnews += 1
                        else:
                            # GNews 无覆盖 → Google RSS + meta 兜底（免费）
                            g = google_news(w, 1)
                            if g:
                                if not is_low_quality_summary(g[0]['title'], g[0]['summary']):
                                    material = g[0]['summary']
                                    r = {'title': g[0]['title'], 'summary': material or w,
                                         'source': g[0]['source'] or 'Google 新闻'}
                                    src_google += 1
                                else:
                                    src_lowq += 1
                                    d = fetch_meta_description(g[0].get('url'))
                                    if d:
                                        material = d
                                        r = {'title': g[0]['title'], 'summary': d,
                                             'source': g[0]['source'] or 'Google 新闻'}
                                        src_meta += 1
                    else:
                        # 原管线（默认）：Google RSS → meta → 腾讯反查
                        g = google_news(w, 1)
                        if g:
                            if not is_low_quality_summary(g[0]['title'], g[0]['summary']):
                                material = g[0]['summary']
                                r = {'title': g[0]['title'], 'summary': g[0]['summary'],
                                     'source': g[0]['source'] or 'Google 新闻'}
                                src_google += 1
                            else:
                                src_lowq += 1
                                d = fetch_meta_description(g[0].get('url'))
                                if d and not is_low_quality_summary(w, d):
                                    material = d
                                    r = {'title': g[0]['title'], 'summary': d,
                                         'source': g[0]['source'] or 'Google 新闻'}
                                    src_meta += 1
                except Exception:
                    r = None
                # DS 摘要：把检索到的素材压成一句客观事实（仅替换摘要文本，来源保留真实媒体）
                if r and use_ds and material and len(material) >= 8:
                    ds = summarize_with_ds(w, material, r.get('source'))
                    if ds:
                        r['summary'] = ds
                        src_ds += 1
                if not r or not r.get('summary'):
                    # 最后兜底：腾讯 search（消耗积分）
                    tn = search_tn_summary(w)
                    if tn:
                        r = {'title': tn.get('title', w), 'summary': tn['summary'],
                             'source': tn.get('source') or '腾讯新闻'}
                        src_tn += 1
                if r and r.get('summary'):
                    entry = {'summary': r['summary'], 'source': r['source'], 'ts': now_ts}
                    it['summary'] = r['summary']
                    it['sum_src'] = r['source']
                    it['sum_ts'] = now_ts
                    seen[w] = entry
                    enriched += 1
                else:
                    if cached:
                        it['summary'] = cached['summary']
                        it['sum_src'] = cached['source']
                        it['sum_ts'] = cached['ts']
                        seen[w] = cached
                    failed += 1
    results.append("摘要: 新搜%d(GNews %d/Google %d/网页meta %d/腾讯 %d/DS压 %d/低质丢弃 %d) 复用%d 失败%d" % (
        enriched, src_gnews, src_google, src_meta, src_tn, src_ds, src_lowq, reused, failed) if enrich else "摘要反查跳过（ENRICH_SUMMARIES 未开启）")

    data = {
        "date": f"{now.year}年{now.month}月{now.day}日 星期{'一二三四五六日'[now.weekday()]}",
        "fetchedAt": now.strftime("%Y年%m月%d日 %H:%M（北京时间）"),
        "platforms": platforms,
    }
    # 双写：/tmp 供本班生成；./hotlists.json 随仓库提交，作为下一班缓存
    for out in ("/tmp/hotlists.json", os.path.join(os.getcwd(), "hotlists.json")):
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    print(" | ".join(results))
    print("total platforms:", len(platforms), "| total items:", sum(len(p["items"]) for p in platforms))

if __name__ == "__main__":
    import urllib.parse  # noqa
    main()
