#!/bin/bash
# ============================================
# AI-FDE Engine 数据备份脚本
# 用法: ./backup.sh [备份目录]
# ============================================

set -e

BACKUP_DIR="${1:-/data/backups/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$BACKUP_DIR"

echo "=========================================="
echo "AI-FDE Engine 数据备份"
echo "备份目录: $BACKUP_DIR"
echo "=========================================="

# 1. PostgreSQL备份
echo "[1/5] 备份PostgreSQL..."
docker exec aifde-postgresql pg_dump -U "${POSTGRES_USER:-aifde}" "${POSTGRES_DB:-aifde}" 2>/dev/null | gzip > "$BACKUP_DIR/postgresql.sql.gz" || echo "  警告: PostgreSQL备份失败（可能服务未运行）"

# 2. Qdrant快照
echo "[2/5] 备份Qdrant向量数据..."
docker run --rm -v aifde_qdrant-data:/data -v "$BACKUP_DIR":/backup alpine \
    tar czf /backup/qdrant-data.tar.gz -C /data . 2>/dev/null || echo "  警告: Qdrant备份失败"

# 3. MinIO备份
echo "[3/5] 备份MinIO对象存储..."
docker run --rm -v aifde_minio-data:/data -v "$BACKUP_DIR":/backup alpine \
    tar czf /backup/minio-data.tar.gz -C /data . 2>/dev/null || echo "  警告: MinIO备份失败"

# 4. Redis备份
echo "[4/5] 备份Redis..."
docker exec aifde-redis redis-cli BGSAVE 2>/dev/null || true
sleep 2
docker run --rm -v aifde_redis-data:/data -v "$BACKUP_DIR":/backup alpine \
    tar czf /backup/redis-data.tar.gz -C /data . 2>/dev/null || echo "  警告: Redis备份失败"

# 5. 配置文件备份
echo "[5/5] 备份配置文件..."
cp .env "$BACKUP_DIR/env.backup" 2>/dev/null || true
cp docker-compose.yml "$BACKUP_DIR/" 2>/dev/null || true

# 备份信息
echo ""
echo "备份完成!"
echo "备份文件:"
ls -lh "$BACKUP_DIR"
echo ""
echo "总大小: $(du -sh "$BACKUP_DIR" | cut -f1)"

# 清理30天前的备份（可选）
# find /data/backups -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;
