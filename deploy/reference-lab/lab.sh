#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec docker compose --env-file private/runtime.env -f compose.yaml -f mumu/compose-fragment.yml -f lite/compose-fragment.yml "$@"
