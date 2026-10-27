#!/bin/sh
set -eu
umask 077
cd /opt/lottery
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="backups/$stamp"
mkdir "$target"
docker compose -f deploy/compose.yaml exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF lottery' > "$target/lottery.sql"
tar -czf "$target/artifacts.tar.gz" -C runtime artifacts
sha256sum "$target/lottery.sql" "$target/artifacts.tar.gz" > "$target/SHA256SUMS"
