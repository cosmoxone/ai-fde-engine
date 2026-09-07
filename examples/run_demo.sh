#!/usr/bin/env bash
# ============================================
# AI-FDE Engine API 演示脚本
# 前置：make dev 启动服务（Mock 模式无需 API Key）
# 用法：bash examples/run_demo.sh
# ============================================
set -e

API="${AIFDE_API_URL:-http://localhost:8000}/api/v1"
echo "==> API: $API"

wait_task() {  # $1=task_id  $2=名称  轮询直至完成
  for i in $(seq 1 20); do
    STATUS=$(curl -sf "$API/tasks/$1" | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])")
    [ "$STATUS" = "completed" ] && break
    [ "$STATUS" = "failed" ] && { echo "❌ $2 失败"; exit 1; }
    sleep 1
  done
  echo "==> $2: $STATUS"
}

# 1. 健康检查
echo -e "\n==> [1/7] 健康检查"
curl -sf "$API/health" | python3 -m json.tool | head -6

# 2. 创建项目
echo -e "\n==> [2/7] 创建项目（智能制造质量管理系统）"
PROJECT_ID=$(curl -sf -X POST "$API/projects" \
  -H "Content-Type: application/json" \
  -d '{"name": "智能质检知识库", "client_name": "华宇精密制造", "industry": "制造业"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['project']['id'])")
echo "项目ID: $PROJECT_ID"

# 3. 上传业务文档
echo -e "\n==> [3/7] 上传业务文档"
curl -sf -X POST "$API/projects/$PROJECT_ID/documents" \
  -F "file=@examples/sample-business-doc.md" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('文档已上传:', d['document']['filename'], '| 解析状态:', d['document'].get('parse_status'))"

# 4. 触发调研分析（异步）
echo -e "\n==> [4/7] 触发调研分析"
TASK_ID=$(curl -sf -X POST "$API/projects/$PROJECT_ID/research/run" \
  -H "Content-Type: application/json" \
  -d '{"client_requirements": "构建智能质量知识库，质检员自然语言提问10秒获得检验标准依据"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
wait_task "$TASK_ID" "调研分析"
curl -sf "$API/tasks/$TASK_ID" | python3 -c "
import sys, json
r = json.load(sys.stdin)['task']['result']
so = r.get('structured_output') or {}
print('  需求项:', len(so.get('requirements', [])), '| 流程节点:', len(so.get('business_processes', so.get('processes', []))), '| Benchmark用例:', so.get('benchmark', {}).get('case_count', so.get('benchmark_case_count', 'N/A')))"

# 5. 生成 Benchmark（异步）
echo -e "\n==> [5/7] 生成Benchmark测试集"
TASK_ID=$(curl -sf -X POST "$API/projects/$PROJECT_ID/benchmarks/generate" \
  -H "Content-Type: application/json" -d '{}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
wait_task "$TASK_ID" "Benchmark生成"
curl -sf "$API/tasks/$TASK_ID" | python3 -c "import sys,json; print('  ', json.load(sys.stdin)['task']['result'])"

# 6. 提交 Badcase + 触发夜间迭代（异步）
echo -e "\n==> [6/7] 触发夜间迭代流水线"
BADCASES=$(python3 -c "import json; print(json.dumps(json.load(open('examples/sample-badcases.json'))['badcases']))")
BENCH=$(python3 -c "import json; print(json.dumps(json.load(open('examples/sample-badcases.json'))['benchmark_cases']))")
TASK_ID=$(curl -sf -X POST "$API/projects/$PROJECT_ID/iteration/run" \
  -H "Content-Type: application/json" \
  -d "{\"badcases\": $BADCASES, \"benchmark_cases\": $BENCH}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
wait_task "$TASK_ID" "夜间迭代"
curl -sf "$API/tasks/$TASK_ID" | python3 -c "
import sys, json
r = json.load(sys.stdin)['task']['result']
print(f\"  版本: {r['version']} | 自动修复: {r['auto_fixed']} | 待人工: {r['need_human']} | 门禁: {'✅通过' if r['gate_passed'] else '❌拦截'} | 已部署: {r['deployed']}\")"

# 7. 查看项目进度
echo -e "\n==> [7/7] 项目进度"
curl -sf "$API/projects/$PROJECT_ID/progress" | python3 -m json.tool | head -14

echo -e "\n✅ 演示完成。打开 http://localhost:8000/dashboard 查看控制台与审核工作台。"
