#!/bin/bash
set -euo pipefail

# Vibe Trading deployment script
# Server: 47.115.144.24
# User: root

REGISTRY="crpi-i6pwsm2rbcu2h5uv.cn-shenzhen.personal.cr.aliyuncs.com"
REGISTRY_USER="876337269@qq.com"
REGISTRY_PASSWORD="Gao876337@"
SERVICES=(rsshub vibe-trading market-sync)

echo "========================================="
echo "Vibe Trading deploy"
echo "========================================="
echo ""

echo "Step 1: Log in to Aliyun ACR..."
echo "${REGISTRY_PASSWORD}" | docker login \
  --username="${REGISTRY_USER}" \
  --password-stdin \
  "${REGISTRY}"
echo "ACR login OK"
echo ""

echo "Step 2: Locate project directory..."
PROJECT_DIR=$(find /opt /root /home -name "Vibe-Trading" -type d 2>/dev/null | head -1)
if [ -z "${PROJECT_DIR}" ] && [ -d "/opt/sigmx" ]; then
  PROJECT_DIR="/opt/sigmx"
fi
if [ -z "${PROJECT_DIR}" ]; then
  echo "Project directory not found. Expected /opt/sigmx or a Vibe-Trading checkout."
  exit 1
fi
echo "Project directory: ${PROJECT_DIR}"
cd "${PROJECT_DIR}"
echo ""

echo "Step 3: Update deployment checkout..."
if [ -d ".git" ]; then
  git fetch origin main
  git pull --ff-only origin main
else
  echo "Not a git checkout; using the existing files in ${PROJECT_DIR}"
fi
echo ""

echo "Step 4: Validate compose services..."
for service in "${SERVICES[@]}"; do
  if ! docker compose config --services | grep -qx "${service}"; then
    echo "Missing required compose service: ${service}"
    exit 1
  fi
done
echo "Required services present: ${SERVICES[*]}"
echo ""

echo "Step 5: Pull latest images..."
docker compose pull "${SERVICES[@]}"
echo ""

echo "Step 6: Start application and data sync worker..."
docker compose up -d --remove-orphans "${SERVICES[@]}"
echo ""

echo "Step 7: Service status..."
docker compose ps
echo ""

echo "Step 8: Recent logs..."
docker compose logs --tail=80 vibe-trading market-sync
