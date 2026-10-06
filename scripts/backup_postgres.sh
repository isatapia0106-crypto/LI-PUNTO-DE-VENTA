#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
mkdir -p backups/postgres
backup_file="backups/postgres/LI-POS-$(date -u +%Y%m%d-%H%M%S)-$$.dump"
partial_file="${backup_file}.partial"
trap 'rm -f -- "$partial_file"' EXIT
umask 077
docker compose --env-file .env.production -f infrastructure/compose.production.yml exec -T db pg_dump -U pos -d pos -Fc > "$partial_file"
docker compose --env-file .env.production -f infrastructure/compose.production.yml exec -T db pg_restore --list < "$partial_file" > /dev/null
mv -- "$partial_file" "$backup_file"
sha256sum "$backup_file" > "${backup_file}.sha256"
echo "Respaldo PostgreSQL creado: $backup_file"
