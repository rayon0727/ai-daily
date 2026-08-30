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


def summarize_with_ds(title, text, source='', api_key=None,
                       base='https://api.deepseek.com', model='deepseek-chat'):
    """用 DeepSeek 把「标题 + 素材」压成一句客观中文摘要（≤40字，只陈述事实）。

    不联网、不检索——只做摘要，因此必须喂入真实素材（news 片段 / meta / 正文）。
    无 key / 异常 / 素材过短 / 退化为标题本身时返回 None，由调用方回退腾讯反查。"""
    if not api_key:
        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return None
    text = (text or '').strip()
    if len(text) < 8:
        return None
    sys_p = ('你是新闻编辑。根据给定标题和素材，写一句客观中文摘要，不超过40字，'
             '只陈述事实、不评论、不添加素材之外的信息。若素材不足以概括，输出标题本身。')
    user_p = f"标题：{title}\n来源：{source}\n素材：{text[:800]}"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p}
        ],
        "max_tokens": 80,
        "temperature": 0.3,
        "stream": False
    }, ensure_ascii=False).encode('utf-8')
    try:
        req = urllib.request.Request(
            base.rstrip('/') + '/v1/chat/completions',
            data=body,
            headers={'Authorization': 'Bearer ' + api_key,
                     'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode('utf-8'))
        content = d['choices'][0]['message']['content'].strip().strip('"\'。')
        if not content or content == title:
            return None
        return content[:60]
    except Exception:
        return None


def resolve_google_news_url(gurl):
    """Google News RSS 链接 → 真实文章 URL。

    Google News 的 link 是 news.google.com 重定向，落地页多为 JS 跳转，
    需从页面内 data-n-aurl 或外链解析出真实来源 URL。"""
    try:
        req = urllib.request.Request(gurl, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            final = r.geturl()
            if 'news.google.com' not in final:
                return final  # 已直接跳转到真实站点
            raw = r.read(800000).decode('utf-8', 'ignore')
        # Google 新闻落地页把真实 URL 放在 data-n-aurl（直链或 base64）
        m = re.search(r'data-n-aurl="([^"]+)"', raw)
        if m and 'news.google.com' not in m.group(1):
            return m.group(1)
        # 退一步：页面里的非 Google 外链
        for mm in re.finditer(r'href="(https?://[^"]+)"', raw):
            u = mm.group(1)
            if 'google.com' not in u:
                return u
        return None
    except Exception:
        return None


def fetch_meta_description(url):
    """抓取新闻原网页的 meta description（免费兜底，不依赖腾讯 CLI 积分）。

    Google News 链接先解析出真实文章 URL，再提取 og:description / meta description。
    失败或内容过短返回 None（静默降级，保留原标题）。"""
    if not url:
        return None
    # Google News 重定向链接：先解析真实文章 URL
    if 'news.google.com' in url:
        real = resolve_google_news_url(url)
        if not real or 'news.google.com' in real:
            return None
        url = real
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(400000).decode('utf-8', 'ignore')
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


def fetch_article_body(url, max_chars=1200):
    """抓取新闻原页正文（免费，不依赖腾讯 CLI 积分）。

    从 HTML 抽取 <p> 段落文本，过滤脚本/导航/页脚，供 DS 摘要使用真实素材，
    避免纯标题导致的幻觉。Google News 重定向链接先解析真实文章 URL。
    非网页（图片/PDF）或二进制残留（PNG/JPEG 头）一律返回 None，交上层回退腾讯。
    失败 / 正文过短（<40 字）返回 None。"""
    if not url:
        return None
    if 'news.google.com' in url:
        url = resolve_google_news_url(url)
    if not url or 'news.google.com' in url:
        return None
    # 图片直链直接跳过
    if re.search(r'\.(png|jpe?g|gif|webp|svg|bmp)(\?|$)', url, re.I):
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            ctype = (r.headers.get('Content-Type') or '').lower()
            if 'text/html' not in ctype and 'text/plain' not in ctype:
                return None  # 非网页（图片/PDF 等）→ 跳过，回退腾讯
            raw = r.read(800000)
        if b'\x00' in raw[:1024]:
            return None  # 含 NUL → 二进制文件，非 HTML
        raw = raw.decode('utf-8', 'ignore')
        # 去掉 script/style/head/nav/footer/header/aside/noscript
        cleaned = re.sub(r'<(script|style|head|nav|footer|header|aside|noscript)[^>]*>.*?</\1>',
                         ' ', raw, flags=re.S | re.I)
        # 优先抽取 <p> 段落文本（新闻正文基本都在 <p> 里）
        paras = re.findall(r'<p[^>]*>(.*?)</p>', cleaned, re.S | re.I)
        texts = []
        for p in paras:
            t = re.sub(r'<[^>]+>', '', p)
            t = html_mod.unescape(t).strip()
            t = re.sub(r'\s+', ' ', t)
            if len(t) >= 15 and not re.search(r'(IHDR|IDAT|JFIF|GIF89|DAT[AM]:IMAGE)', t, re.I):
                texts.append(t)
        body = ' '.join(texts)[:max_chars]
        if len(body) < 40:
            # 退一步：整页去标签取中段文本
            no_tag = re.sub(r'<[^>]+>', ' ', cleaned)
            no_tag = html_mod.unescape(no_tag)
            no_tag = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', no_tag)
            no_tag = re.sub(r'\s+', ' ', no_tag).strip()
            body = no_tag[:max_chars]
        # 终检：仍含图片二进制特征则丢弃
        if re.search(r'(IHDR|IDAT|JFIF|GIF89|DAT[AM]:IMAGE)', body, re.I):
            return None
        return body if len(body) >= 40 else None
    except Exception:
        return None


def gnews_search(q, limit, apikey, lang='zh', country='cn'):
    """GNews API 搜索（免费层 100 次/天，返回真实 description + 直链 url）。

    摘要为真实新闻片段（非标题重复），url 为原站直链，便于网页兜底与点击。
    需要 apikey；无 key 或异常时返回 []，由调用方回退 Google News RSS。"""
    if not apikey:
        return []
    url = ('https://gnews.io/api/v4/search?q=' + urllib.parse.quote(q) +
           f'&lang={lang}&country={country}&max={limit}&apikey={apikey}')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        out = []
        for a in d.get('articles', [])[:limit]:
            published = a.get('publishedAt') or ''
            ts = ''
            try:
                ts = datetime.fromisoformat(published.replace('Z', '+00:00')).astimezone(BJT).strftime('%Y-%m-%d %H:%M')
            except Exception:
                ts = ''
            out.append({'title': a.get('title', ''),
                        'summary': (a.get('description') or '').strip()[:140],
                        'source': (a.get('source') or {}).get('name', ''),
                        'url': a.get('url', ''),
                        'time': ts})
        return out
    except Exception:
        return []


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
        # 清洗 Google News 把来源名拼进 title 的写法（"真实标题 - 来源名"）
        if src and title.endswith(src) and len(src) < len(title):
            title = title[: -len(src)].strip().rstrip('-—–|｜ ').strip()
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

    # 2. 物联网搜索：GNews API（真实摘要，免费层）→ 无 key 时回退 Google News RSS（+腾讯反查+网页兜底）
    GNEWS_KEY = os.environ.get('GNEWS_API_KEY', '')
    for name, q, lang, country in (('cn', '物联网', 'zh', 'cn'),
                                   ('global', 'Internet of Things', 'en', 'us')):
        recs = gnews_search(q, 8, GNEWS_KEY, lang, country) if GNEWS_KEY else []
        if recs:
            txt = to_cli_text(recs)
            tag = f'GNews({len(recs)})'
        else:
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
