# 朝闻 · 访问即更新（Cloudflare Worker）

把晨报站从「每小时/每天盲目自动跑」改成「访问即更新 + 每天保底两次」，在控制配额的同时保证资讯不会太久不刷新。

## 原理
- GitHub Pages 仍是静态源（`https://rayon0727.github.io/ai-daily/`）。
- 本 Worker 挡在前面：你访问时，它先读仓库里的 `build-daily.json` / `build-hot.json`（云端每次构建都会写入时间戳）。
  - 内容超过 `STALE_HOURS`（默认 4 小时）→ 异步触发对应 workflow 重建，**本次仍返回现有内容**，下次访问即最新。
  - 用 KV 记录「上次触发时间」做去抖（默认 10 分钟内不重复触发），避免并发重复跑。
- 路径路由：`/` 或 `/index.html` → 晨报（触发 `daily-report.yml`）；`/hot*`（如 `/hot.html`）→ 热搜（触发 `hotlists.yml`）。其它静态资源（图片/CSS/JS/archive/历史 combined）直接代理，不触发。

## 前提
- 一个 Cloudflare 账号（免费版够用：Workers 10 万请求/天、KV 免费额度）。
- `~/.workbuddy/gh-token` 的内容（fine-grained PAT，仅 `rayon0727/ai-daily` 的 Contents + Actions 读写，已验证可 dispatch）。

## 部署步骤
```bash
# 1. 登录 Cloudflare（浏览器授权）
wrangler login

# 2. 创建 KV 命名空间，记下返回的 id
wrangler kv namespace create ai-daily-kv
#   输出示例：id = "a1b2c3d4..."  → 填进 wrangler.toml 的 id

# 3. 设置机密 GH_TOKEN（粘贴 ~/.workbuddy/gh-token 的内容）
wrangler secret put GH_TOKEN

# 4. 部署
cd worker
wrangler deploy
#   得到地址，例如 https://ai-daily-worker.<sub>.workers.dev/
```

## 使用
- 把书签从 `https://rayon0727.github.io/ai-daily/` 换成 Worker 地址（根路径即晨报）。
- 打开 → 若内容超过 4 小时，后台自动重建；响应头 `x-ai-daily-rebuilding: 1` 表示本次已触发重建，刷新一下即可看到新版。
- 热搜页访问 `https://<worker>/hot.html` 即可按需刷新。

## 触发策略（双保险）
- **保底定时**：两个 workflow 的 `on.schedule` 设了 `cron: '30 1,13 * * *'`（UTC），即**北京时间每天 09:30 与 21:30 各自动重建一次**。即使你很久没访问，资讯最旧也不会超过约 12 小时。
- **访问补充**：Worker 在你打开页面且内容超过 `STALE_HOURS`（默认 4 小时）时，再异步触发一次，让当天频繁查看时更及时。
- 两者并存、互不冲突：定时保证最低频度，Worker 提供按需即时性。

## 关闭旧的自动触发
- 旧的 cron-job.org 定时（给 `daily-report` / `refresh` 的 `repository_dispatch`）**必须停用/删除**，否则会一直 404 报错；它已被 GitHub 原生 `schedule` 取代。
- （可选）若想临时手动跑一次，可在 GitHub 仓库 Actions 页面手动 `Run workflow`，或访问 Worker 触发。
