# Huawei production deployment

Server: `123.249.29.77`, application: `/opt/lottery`.
Public URL: `http://123.249.29.77/`. Nginx also listens on 9998, but the cloud firewall currently blocks external access to that port. Port 80 works; no domain is needed for this endpoint.

Production files: `deploy/compose.yaml`, `deploy/nginx.conf`, `deploy/Dockerfile`.
Build on an amd64-capable machine with `docker build --platform linux/amd64 -f deploy/Dockerfile -t lottery-backend:local .`. Transfer via `docker save`/`docker load` if Docker Hub is unreachable from the server.

Server `.env` contains independently generated MySQL passwords; `backend/.env` contains the internal mysql hostname and existing ServerChan SendKey. Both are mode 600 and excluded from images. Never commit these files.

Operations (on server):

```sh
cd /opt/lottery
docker compose -f deploy/compose.yaml --profile scheduled ps
docker compose -f deploy/compose.yaml logs --tail 100 scheduler
docker compose -f deploy/compose.yaml --profile scheduled up -d --no-build
```

Database is only accessible on server loopback port 9999. Use an SSH tunnel for database tools. API listens on loopback 8000, proxied under `/api/` by Nginx.

Old applications and MySQL were backed up offline in `/root/legacy-backup/legacy-20261023.tar.gz`; SHA256SUMS verifies archive integrity. Old MySQL service is disabled. OS, SSH and Huawei agents are retained.

Do not start the local scheduler while the cloud scheduler runs. Local `scripts/local.py` honors `runtime/cloud-deployed` and skips its scheduler when present. Manual local workflow commands must not be run against a separate database with notifications enabled.

Deployed code as of 2026-10-26 collects and analyzes daily at 22:30 Asia/Shanghai, retrying incomplete data at 23:00, 23:30 and 00:00. Monday/Wednesday/Friday 08:00 reports only read saved valid predictions (five tickets per game). Monthly backtests run on day 1 at 06:00. This schedule is active in production. Candidate strategies are not proven to improve winning probability.

Manual backup on the server: `sh /opt/lottery/deploy/backup.sh`. This writes a transaction-consistent SQL dump plus prediction, research-model and monitoring runtime state under `/opt/lottery/backups`, with SHA-256 checksums. Run `sha256sum -c backups/<timestamp>/SHA256SUMS` from `/opt/lottery`. Download backups regularly; a backup on the same server does not cover server loss.

Deployment verified 2026-10-23: 2,938 DLT + 3,518 SSQ records; both stored prediction snapshots verified; API and scheduler restart verified. First cloud backup: `/opt/lottery/backups/20261023T095330Z`. All three containers have `unless-stopped` restart policy; Docker and Nginx are enabled at boot. Backend tests passed both locally and in the Linux image (39 each).

## Prospective strategy evaluation

Migration `002` adds candidate_forecasts, candidate_scores and strategy_decisions. The regular workflow scores valid frozen forecasts after data synchronization, then generates two candidate forecasts alongside each new official prediction. `python -m lottery.cli evaluate` performs the same prospective evaluation/future shadow initialization without sending notifications. Never count a backtest as forward evidence.

Use `/api/strategies?game=dlt` or `ssq` for read-only status. Minimum 60 settled forecasts, >=1% Brier improvement, a better latest 30-draw window and the version-specific sequential evidence threshold are all required for promotion. Each game budgets alpha across successive model versions. Existing issued predictions never change; replay uses saved probabilities for non-uniform strategies. Invalid candidate generation falls back to uniform. Historical reports retain their original text as audit records.


## 2026-10-26 release

Image `lottery-backend:20261026` (d4e4dec6ab26), also tagged `lottery-backend:local`. Dependencies matched the prior image byte-for-byte; updated source layered on `lottery-backend:pre-20261026` without network installation. Local and production Linux tests: 63 passed each. Migration003 applied. UI assets: index-DnwGKKBI.js / index-8TLE8IWs.css, verified by public SHA256 comparison.

Backup: `/opt/lottery/backups/20261026T035117Z` (SQL and artifacts checksums passed). Prior application files: `backups/pre-20261026-app.tar.gz`; frontend rollback directory: `frontend/dist-pre-20261026`; prior image: `lottery-backend:pre-20261026`. Rollback application code without dropping additive003 tables or replacing current DB; stop scheduler during any rollback.

Live non-notifying workflow run12 succeeded; existing4 formal predictions preserved, notification count remained2. DLT2026122 and SSQ2026123 each have100 frozen5-ticket random control groups. SSQ latest prize7 data remains incomplete and pending; no synthetic zero amount used. Cloud's already-frozen formal tickets intentionally remain authoritative, differing from later local samples.

Public API/asset checks, fresh scheduler heartbeat, native Edge login (wrong/correct), real dashboard, portfolio details, refresh persistence and logout passed. Login remains the requested frontend-only gate, not API authorization.
