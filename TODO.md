# Token Radar — Roadmap / TODO

## 已完成（确定、已上线）
- [x] OpenRouter rankings-daily + app-rankings 自动拉取（需 OR API key，已配 Actions secret）
- [x] 模型 landscape（公开 /models）
- [x] 单文件 dashboard（ECharts）+ GitHub Pages 公开 URL
- [x] GitHub Actions 每 3 小时自动刷新 + 自动重建 Pages
- [x] 宏观 macro 区：Google 月度 token、字节豆包 180万亿/日、火山引擎 MaaS 份额

## GPU 租赁价（待用户决策）
- [ ] **首选**：买 Silicon Data API → 接真实 SDH100RT / SDB200RT 指数（权威，与用户现用图一致）
  - 买前确认 license 是否允许公开页转发指数值；不允许则做**私有/本地版**，公开页不放
- [ ] 可选补充：vast.ai 免费市场现货线（H100/B200 marketplace floor），与 Silicon Data 指数做 **floor-vs-index 价差信号**（价差走阔/收窄本身有含义）
- 结论：Silicon Data = benchmark（权威），vast.ai = signal（免费现货下沿，低 35-50%）

## 待做模块（用户已确认放 todo，先做确定的）
- [ ] **中国模型 token 份额（CN vs 海外）** — 免费，用现有 rankings 数据；DeepSeek/Qwen/Kimi/MiniMax/智谱/腾讯/小米/百度/阶跃等归 CN，画份额日线。【优先推荐】
- [ ] 开源 vs 闭源 token 份额 — 需一份可审计的 open/closed 映射表
- [ ] Coding agent 占 token 比 — 从 app 排名聚合 Cline/Kilo Code/Claude Code/OpenClaw 等
- [ ] 更多第一方披露进 macro — OpenAI/Anthropic ARR、百度文心、阿里通义、腾讯混元（带 source + 待核实标记）

## 候选数据源（评估中，多为低频/手动，进 macro 做交叉验证）
- Artificial Analysis（模型质量/价格/速度基准，有结构化数据，可能可自动）
- Epoch AI（训练算力/前沿趋势）
- SemiAnalysis（GPU/capex，部分付费）
- 各家财报 + 大会披露（一手；海外读英文原文，中国读一手中文披露）

## 已知 caveat（对外交付时讲清）
- token 数按各上游 tokenizer 计，跨模型不严格可比
- OpenRouter 是第三方聚合层，看结构非市场总量；第一方与直签企业不在内
- rankings-daily 是每日粒度，"高频"= 尽快拿当日结算值，非日内分辨率
- GitHub Actions cron 是 best-effort，可能延迟/偶尔跳过
- macro 区 Google 数字仍标 待核实（本会话未二次核实）；豆包 180万亿/日 已核实（火山引擎 2026-06 披露）
