#!/usr/bin/env bash
# e2e 验证：金币随时间流逝 + 损失分类（v0.3.4）
# 用法：bash tests/e2e_coin_loss.sh <exe路径> <临时数据目录>
set -u
EXE="$1"
DATADIR="$2"
PORT=18765
export LIFEMGR_DATA_DIR="$DATADIR"
export LIFEMGR_PORT="$PORT"
# 注意：打包后的 EXE 会自行决定 frontend/data 目录（main.js 覆盖 env），以下仅 dev 模式生效
mkdir -p "$DATADIR"
BASE="http://127.0.0.1:$PORT"

echo "== 启动 EXE: $EXE =="
"$EXE" >"_tmp_e2e.log" 2>&1 &
EXEPID=$!
cleanup() { kill "$EXEPID" 2>/dev/null; }
trap cleanup EXIT

echo "== 等待健康检查 =="
for i in $(seq 1 120); do
  if curl -s "$BASE/health" >/dev/null 2>&1; then echo "health OK (${i}x0.5s)"; break; fi
  sleep 0.5
done

echo "== 注册 =="
REG=$(curl -s -X POST "$BASE/api/register" --data-binary @tests/e2e_reg.json)
echo "$REG" | head -c 300; echo

echo "== 登录取 token =="
TOK=$(curl -s -X POST "$BASE/api/login" --data-binary @tests/e2e_login.json | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{try{console.log(JSON.parse(s).token||'')}catch(e){console.log('')}})")
echo "token len=${#TOK}"
AUTH="-H Authorization:Bearer $TOK"

echo "== 添加带时长任务（120 分钟 = 2 金币）=="
curl -s -X POST "$BASE/api/tasks?date=$(date +%F)" $AUTH --data-binary @tests/e2e_task.json | head -c 200; echo

echo "== 日回顾（校验 time_elapsed / used / lost / remaining）=="
curl -s "$BASE/api/review?range=day" $AUTH | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const j=JSON.parse(s);console.log(JSON.stringify({budget:j.budget,time_elapsed:j.time_elapsed,used:j.used,lost:j.lost,remaining:j.remaining,by_category:j.by_category.map(c=>c.category)},null,2));const ok = typeof j.time_elapsed==='number' && typeof j.lost==='number' && j.used>=2 && j.remaining<=j.budget && (j.lost>=0);console.log('CHECKS time_elapsed?used>=2?remaining<=budget?lost>=0? =>', ok);})"

echo "== 关闭 EXE =="
