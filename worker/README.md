# 朝闻 · 访问即更新（Cloudflare Worker）

把晨报站从「定时自动跑」改成「只有打开页面时才可能触发重建」，彻底停止无意义的配额/算力消耗。

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

## 关闭旧的自动触发
- 仓库两个 workflow 已移除 `schedule` 定时与 `repository_dispatch`，不再自动跑。
- 务必到 **cron-job.org** 把原来给 `daily-report` / `refresh` 的定时任务**停用/删除**，否则它们会继续 404。
- （可选）若想临时手动跑一次，可在 GitHub 仓库 Actions 页面手动 `Run workflow`。
