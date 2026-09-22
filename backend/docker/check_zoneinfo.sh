#!/bin/sh
# Resolve an IANA zone inside the API image. Host timezone data must not be used.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
docker compose -f "$root/docker-compose.yml" run --rm --no-deps --entrypoint python3 api -c \
  "from zoneinfo import ZoneInfo; zone = ZoneInfo('America/Mexico_City'); assert str(zone) == 'America/Mexico_City', zone; print(zone)"
