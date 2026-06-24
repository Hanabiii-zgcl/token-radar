# Token Radar

一个每天/高频自动刷新的 AI token 使用追踪 dashboard。对标 OpenRouter，但把口径分层讲清楚：第三方聚合层（OpenRouter，可自动）+ 模型 landscape（公开，可自动）+ 宏观第一方背景（人工维护）。

零依赖：纯 Python 标准库 + 单文件 HTML（ECharts via CDN）。

## 数据源（已对官方 OpenAPI spec 核实，2026-06）

| 区块 | 端点 | 认证 | 自动化 |
|---|---|---|---|
| Token 排名（每日 Top50 模型 token 量） | `GET /api/v1/datasets/rankings-daily` | OpenRouter API key（Bearer） | ✅ |
| 应用排名（按 token 的 app） | `GET /api/v1/datasets/app-rankings` | OpenRouter API key（Bearer） | ✅ |
| 模型 landscape（339 模型/定价/发布） | `GET /api/v1/models` | 公开，无需 key | ✅ |
| 宏观口径（Google 等第一方披露） | — | 手动 | 编辑 `data/macro.json` |

`rankings-daily` 支持 `start_date/end_date`，首次运行即回填 90 天历史 → 时间序列图第一天就有，不用等。

> **口径诚实声明**：token 数按各上游模型自己的 tokenizer 计，跨模型不严格可比。OpenRouter 是第三方聚合层，看结构与趋势，**不代表市场总量**——第一方(ChatGPT/Claude.ai/Gemini app)与直签企业大单都不在内。`rankings-daily` 底层是**每日**粒度，高频刷新是为了尽快拿到当日结算值 + 快速发现新模型，不会造出日内分辨率。

## 快速开始

```bash
# 1) 拿一个 OpenRouter key（免费）：https://openrouter.ai/keys
echo "OPENROUTER_API_KEY=sk-or-xxxx" > .env

# 2) 一键拉数 + 起本地服务器
./run.sh
# 打开 http://localhost:8787
```

没有 key 也能跑——只点亮「模型 landscape」半区，token 排名半区会提示如何开启。
看板也可直接**双击 `index.html`** 离线打开（`data.js` 用 `<script src>` 加载，file:// 也能读）。

## 高频自动刷新

**方式 A · GitHub Actions + Pages（推荐，免费、有公开 URL、自动归档历史）**
1. 把本目录推到一个 GitHub repo。
2. repo → Settings → Secrets and variables → Actions → 新建 `OPENROUTER_API_KEY`。
3. repo → Settings → Pages → Source 选 `Deploy from a branch` → `main` / root。
4. `.github/workflows/update.yml` 每 3 小时自动跑、提交刷新后的 `data.js`，Pages 自动更新。

**方式 B · 本地 launchd（不依赖 GitHub）**
编辑 `com.tokenradar.refresh.plist` 里的 key 和路径，然后：
```bash
cp com.tokenradar.refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tokenradar.refresh.plist
```
每 3 小时跑一次，双击 `index.html` 看最新。

## 结构

```
fetch.py            # 抓取 + 聚合，产出 data.js / data/latest.json / data/snapshots/
index.html          # 单文件看板（读 data.js）
data/macro.json     # 人工维护的宏观参考量（带 source + 待核实标记）
data/snapshots/     # 每次运行的原始快照归档（>90 天历史靠它）
.github/workflows/  # 定时刷新
```

## 后续可扩展
- 多源：接 Artificial Analysis / Epoch AI / 各家财报 ARR 做交叉验证（目前 macro.json 占位）。
- 开源 vs 闭源 token 份额（需对 provider 做 open/closed 映射，当前按 provider 分组，未做此切分）。
- 把每日变化做成 skill 推送（和现有 social-alpha-radar 日报体例打通）。
