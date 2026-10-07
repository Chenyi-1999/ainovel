#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
chmod 700 backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T db pg_dump -U ainovel -d ainovel -Fc > "backups/ainovel-$stamp.dump"
chmod 600 "backups/ainovel-$stamp.dump"
echo "Backup saved: backups/ainovel-$stamp.dump"
