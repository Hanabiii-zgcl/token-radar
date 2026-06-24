#!/usr/bin/env bash
# 本地一键：拉数据 + 起静态服务器看 dashboard
set -e
cd "$(dirname "$0")"

# 读取本地 key（可选）：把 OPENROUTER_API_KEY=sk-or-... 写进 .env
[ -f .env ] && export $(grep -v '^#' .env | xargs)

python3 fetch.py
echo
echo ">> dashboard: http://localhost:8787"
echo ">> Ctrl-C 退出"
python3 -m http.server 8787
