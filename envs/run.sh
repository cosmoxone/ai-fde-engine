#!/usr/bin/env bash
# 环境统一入口：envs/run.sh <local|preview|dev|test|prod> <ce|te> <up|down|restart|ps|logs|seed|config>
# 设计：envs/README.md（矩阵/纪律）。源码形态=nohup+PID 记录（P-3/坑17 纪律）；dev=compose 栈托管。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="${1:?用法: envs/run.sh <local|preview|dev|test|prod> <ce|te> <up|down|restart|ps|logs|seed|config>}"
FORM="${2:?ce|te}"
ACTION="${3:-ps}"
ENVFILE="$ROOT/envs/$ENV.env"
[ -f "$ENVFILE" ] || { echo "未知环境 $ENV（可选 local/preview/dev/test/prod）"; exit 1; }
# shellcheck disable=SC1090
source "$ENVFILE"
TAG="$ENV-$FORM"
PIDFILE="$ROOT/envs/run/$TAG.pid"
LOGFILE="$ROOT/envs/run/$TAG.log"

_ce_port() { echo "${CE_PORT:-8000}"; }
_te_port() { echo "${TE_PORT:-8014}"; }
_port() { [ "$FORM" = ce ] && _ce_port || _te_port; }
_datadir() { echo "${DATA_PREFIX:-data_run}_${FORM}"; }

_src_up() {  # 源码形态（local/preview/test）
  local port; port="$(_port)"
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[$TAG] 已在运行 (PID $(cat "$PIDFILE"), :$port)"; return 0
  fi
  local dd; dd="$(_datadir)"
  cd "$ROOT"
  if [ "$FORM" = ce ]; then
    [ "${CE_USERS:-false}" = true ] && export LOCAL_USERS_ENABLED=true || unset LOCAL_USERS_ENABLED
    unset AUTH_PROVIDER
    nohup .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port "$port" >>"$LOGFILE" 2>&1 &
  else
    export AUTH_PROVIDER=local ADMIN_INVITE_CODE="${ADMIN_INVITE_CODE:?TE local/test 需 ADMIN_INVITE_CODE}"
    unset LOCAL_USERS_ENABLED
    nohup .venv/bin/uvicorn ee.src.main:app --host 0.0.0.0 --port "$port" >>"$LOGFILE" 2>&1 &
  fi
  echo $! > "$PIDFILE"
  sleep 3
  curl -sf -m 3 "http://localhost:$port/api/v1/health" >/dev/null && echo "[$TAG] ✓ 运行于 :$port（PID $(cat "$PIDFILE")，数据 $dd，日志 $LOGFILE）"
  if [ "${DEMO_SEED:-false}" = true ]; then
    local extra=""
    [ "$FORM" = te ] && [ "$ENV" = dev ] && extra="--casdoor http://localhost:${CASDOOR_PORT:-17100}"
    python3 "$ROOT/demo/seed.py" --mode "$FORM" --base "http://localhost:$port" $extra || true
  fi
}

_src_down() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" && rm -f "$PIDFILE" && echo "[$TAG] ✓ 已停止（数据保留 $(_datadir)）"
  else
    rm -f "$PIDFILE"; echo "[$TAG] 未在运行"
  fi
}

_compose_dir() { [ "$FORM" = ce ] && echo "$ROOT/deploy/ce-standalone" || echo "$ROOT/ee/deploy/te-saas"; }

case "$ENV" in
  local|preview|test)
    case "$ACTION" in
      up) _src_up ;;
      down) _src_down ;;
      restart) _src_down || true; _src_up ;;
      ps) [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null && echo "[$TAG] 运行中 :$(_port) (PID $(cat "$PIDFILE"))" || echo "[$TAG] 未运行" ;;
      logs) tail -n 40 "$LOGFILE" 2>/dev/null || echo "无日志" ;;
      seed) local extra=""; [ "$FORM" = te ] && [ "$ENV" = dev ] && extra="--casdoor http://localhost:${CASDOOR_PORT:-17100}"
            python3 "$ROOT/demo/seed.py" --mode "$FORM" --base "http://localhost:$(_port)" $extra ;;
      *) echo "动作不支持：$ACTION"; exit 1 ;;
    esac ;;
  dev)
    D="$(_compose_dir)"
    case "$ACTION" in
      up) (cd "$D" && export BUILD_COMMIT="${BUILD_COMMIT:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)}" && docker compose up -d) ;;
      down) (cd "$D" && docker compose down) ;;
      ps) (cd "$D" && docker compose ps) ;;
      logs) (cd "$D" && docker compose logs --tail 40 "$([ "$FORM" = ce ] && echo aifde-ce || echo te)") ;;
      seed) local extra=""; [ "$FORM" = te ] && [ "$ENV" = dev ] && extra="--casdoor http://localhost:${CASDOOR_PORT:-17100}"
            python3 "$ROOT/demo/seed.py" --mode "$FORM" --base "http://localhost:$(_port)" $extra ;;
      *) echo "动作不支持：$ACTION"; exit 1 ;;
    esac ;;
  prod)
    case "$ACTION" in
      config)
        echo "== prod 配置校验（$FORM）=="
        grep -E '^[A-Z_]+=' "$ENVFILE" | while IFS='=' read -r k v; do
          [ -z "$v" ] && echo "✗ $k 未设置" || echo "✓ $k=${v:0:24}…"
        done
        echo "（生产部署见 $(_compose_dir)/README 生产清单；本命令不起容器）" ;;
      *) echo "prod 仅支持 config（生产不在本机起）"; exit 1 ;;
    esac ;;
esac
