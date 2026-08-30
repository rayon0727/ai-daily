// 朝闻 · 访问即更新 Worker
// stale-while-revalidate：用户访问时，若构建产物超过 STALE_HOURS 则异步触发云端重建，
// 本次仍返回现有（可能稍旧）内容，下次访问即最新。KV 做去抖，避免并发重复触发。
//
// 依赖（在 Cloudflare 侧配置）：
//   - 环境变量/机密 GH_TOKEN：fine-grained PAT（仅 ai-daily 仓库 Contents+Actions 读写）
//   - KV 绑定：变量名 KV（用于存储各 workflow 上次触发时间做去抖）

const REPO = 'rayon0727/ai-daily';
const ORIGIN = 'https://rayon0727.github.io/ai-daily';
const STALE_HOURS = 4;     // 超过这么久没构建才触发
const DEBOUNCE_MIN = 10;   // 同一 workflow 两次触发最小间隔（分钟）
const KV_KEY = { daily: 'daily_last_trigger', hot: 'hot_last_trigger' };

async function getBuildTs(kind) {
  const f = kind === 'daily' ? 'build-daily.json' : 'build-hot.json';
  try {
    const r = await fetch(`https://raw.githubusercontent.com/${REPO}/main/${f}`, { cf: { cacheTtl: 60 } });
    if (!r.ok) return 0;
    const j = await r.json();
    return j.ts || 0;
  } catch {
    return 0;
  }
}

async function maybeTrigger(env, kind) {
  const now = Date.now();
  const ts = await getBuildTs(kind);
  if (ts && now - ts * 1000 < STALE_HOURS * 3600 * 1000) return false; // 还新鲜
  const last = Number(await env.KV.get(KV_KEY[kind]) || '0');
  if (now - last < DEBOUNCE_MIN * 60 * 1000) return false;            // 去抖
  await env.KV.put(KV_KEY[kind], String(now));
  const wf = kind === 'daily' ? 'daily-report.yml' : 'hotlists.yml';
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${wf}/dispatches`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.GH_TOKEN}`,
          Accept: 'application/vnd.github+json',
          'Content-Type': 'application/json',
          'X-GitHub-Api-Version': '2022-11-28',
        },
        body: JSON.stringify({ ref: 'main' }),
      }
    );
    return resp.ok;
  } catch {
    return false;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const isDebug = url.searchParams.has('debug');
    let kind = null;
    if (path === '/' || path === '/index.html') kind = 'daily';
    else if (path.startsWith('/hot')) kind = 'hot';

    let triggered = false;
    let triggerErr = null;
    if (kind) {
      try {
        triggered = await maybeTrigger(env, kind);
      } catch (e) {
        triggerErr = String(e);
      }
    }

    const target = ORIGIN + (path === '/' ? '/index.html' : path);

    // 用目标 URL 新建 Request，确保 Host 头是 rayon0727.github.io 而不是 workers.dev。
    // 不转发 Accept-Encoding，避免压缩透传问题；不转发 Cookie/Authorization。
    const upstreamReq = new Request(target, {
      method: 'GET',
      headers: {
        'Accept': request.headers.get('Accept') || 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': request.headers.get('Accept-Language') || 'zh-CN,zh;q=0.9,en;q=0.8',
        'User-Agent': request.headers.get('User-Agent') || 'Mozilla/5.0 (compatible; Cloudflare-Worker)',
      },
    });

    let resp;
    let fetchErr = null;
    try {
      resp = await fetch(upstreamReq);
    } catch (e) {
      fetchErr = String(e);
    }

    // debug 模式：返回上游请求/响应的调试信息（便于排查白屏）
    if (isDebug) {
      const bodyPreview = resp && resp.body ? '(stream)' : 'none';
      return new Response(JSON.stringify({
        worker: 'ai-daily-worker',
        path,
        kind,
        target,
        triggered,
        triggerErr,
        fetchErr,
        upstreamStatus: resp ? resp.status : null,
        upstreamStatusText: resp ? resp.statusText : null,
        upstreamHeaders: resp ? Object.fromEntries(resp.headers.entries()) : null,
        bodyPreview,
      }, null, 2), {
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
      });
    }

    // 若上游抓取失败或返回空 body，直接 302 跳回 GitHub Pages 原址，保证用户一定能看到内容。
    if (!resp || !resp.ok || !resp.body) {
      return Response.redirect(target, 302);
    }

    const h = new Headers(resp.headers);
    if (kind) {
      h.set('Cache-Control', 'public, max-age=300');
      if (triggered) h.set('x-ai-daily-rebuilding', '1');
    }
    return new Response(resp.body, { status: resp.status, headers: h });
  },
};
