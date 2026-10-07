#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then echo "Usage: scripts/restore.sh backups/ainovel-TIMESTAMP.dump"; exit 1; fi
cd "$(dirname "$0")/.."
test -f "$1"
echo "Stopping API and worker during database restore"
docker compose stop api worker
trap 'docker compose start api worker' EXIT
docker compose exec -T db pg_restore -U ainovel -d ainovel --clean --if-exists < "$1"
echo "Restore completed"
