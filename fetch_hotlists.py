#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全网热搜抓取：微博 + 今日头条 Top10（每日快照）
输出: /tmp/hotlists.json  {date, fetchedAt, platforms:[{key,name,color,icon,note,items:[{rank,word,hot,label,url}]}]}
失败平台自动降级（items=[] 或跳过），不中断。
抖音：官方接口需签名、第三方聚合当前网络不可达 → 暂不接入（留 key 占位，后续补）。
"""
import json, re, sys, urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
TIMEOUT = 12
TOP_N = 10

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

    from datetime import datetime, timezone, timedelta
    bjt = timezone(timedelta(hours=8))
    now = datetime.now(bjt)
    data = {
        "date": f"{now.year}年{now.month}月{now.day}日 星期{'一二三四五六日'[now.weekday()]}",
        "fetchedAt": now.strftime("%Y年%m月%d日 %H:%M（北京时间）"),
        "platforms": platforms,
    }
    with open("/tmp/hotlists.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(" | ".join(results))
    print("total platforms:", len(platforms), "| total items:", sum(len(p["items"]) for p in platforms))

if __name__ == "__main__":
    import urllib.parse  # noqa
    main()
