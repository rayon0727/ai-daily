#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全网热搜抓取：微博 + 今日头条 Top10（每日快照）
输出: /tmp/hotlists.json  {date, fetchedAt, platforms:[{key,name,color,icon,note,items:[{rank,word,hot,label,url}]}]}
失败平台自动降级（items=[] 或跳过），不中断。
抖音：官方接口需签名、第三方聚合当前网络不可达 → 暂不接入（留 key 占位，后续补）。
"""
import json, re, sys, os, shutil, subprocess, urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
TIMEOUT = 12
TOP_N = 10
CACHE_HOURS = 24  # 摘要缓存有效期：24 小时内同一热词不重复搜索

def load_summary_cache():
    """从上次结果（仓库 ./hotlists.json 或 /tmp/hotlists.json）读取 word -> 摘要缓存"""
    cache = {}
    for cand in (os.path.join(os.getcwd(), "hotlists.json"), "/tmp/hotlists.json"):
        if not os.path.exists(cand):
            continue
        try:
            old = json.load(open(cand, encoding="utf-8"))
            for pl in old.get("platforms", []):
                for it in pl.get("items", []):
                    w = (it.get("word") or "").strip("#").strip()
                    if w and it.get("summary"):
                        cache[w] = {"summary": it["summary"], "source": it.get("sum_src", ""),
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
    for name, fn in (("微博", fetch_weibo), ("头条", fetch_toutiao)):
        try:
            p = fn()
            platforms.append(p)
            results.append(f"{name} OK ({len(p['items'])} 条)")
        except Exception as e:
            results.append(f"{name} FAIL ({type(e).__name__}: {str(e)[:80]})")

    # 热词反查摘要（方案 A：智能增量）：每平台 Top5 全局去重；
    # 24h 内已反查过的词直接复用缓存（不消耗积分），只搜新词/过期词。
    # 由 ENRICH_SUMMARIES=1 开启（云端每班执行）。
    from datetime import datetime, timezone, timedelta
    bjt = timezone(timedelta(hours=8))
    now = datetime.now(bjt)
    now_ts = int(now.timestamp())

    enrich = os.environ.get('ENRICH_SUMMARIES', '0') == '1'
    cache = load_summary_cache() if enrich else {}
    seen = {}
    reused = enriched = failed = 0
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
                    # 缓存命中（24h 内）：复用，不搜索
                    it['summary'] = cached['summary']
                    it['sum_src'] = cached['source']
                    it['sum_ts'] = cached['ts']
                    seen[w] = cached
                    reused += 1
                    continue
                r = search_tn_summary(w)
                if r:
                    entry = {'summary': r['summary'], 'source': r['source'], 'ts': now_ts}
                    it['summary'] = r['summary']
                    it['sum_src'] = r['source']
                    it['sum_ts'] = now_ts
                    seen[w] = entry
                    enriched += 1
                else:
                    # 搜索失败（如积分不足）：有旧缓存则兜底复用，否则留空
                    if cached:
                        it['summary'] = cached['summary']
                        it['sum_src'] = cached['source']
                        it['sum_ts'] = cached['ts']
                        seen[w] = cached
                    failed += 1
    results.append(f"摘要: 新搜{enriched} 复用{reused} 失败{failed}" if enrich else "摘要反查跳过（ENRICH_SUMMARIES 未开启）")

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
