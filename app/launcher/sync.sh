#!/bin/sh
# Sync CLI (Linux). Usage: sync.sh up | down | status | settings | gui-url | env | ctx | remote-url | api | doctor | chat
# Uses the bundled Python (../python/bin/python3) when installed; otherwise python3 from the system.
D="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$D/../python/bin/python3" ]; then
  exec "$D/../python/bin/python3" -s -X utf8 "$D/sync.py" "$@"
fi
exec python3 -X utf8 "$D/sync.py" "$@"
