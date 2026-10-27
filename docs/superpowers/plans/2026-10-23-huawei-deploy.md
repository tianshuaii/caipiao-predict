# Huawei deployment implementation plan

> Execute inline with superpowers:executing-plans; user authorized cleanup and deployment.

Goal: Serve the existing lottery application publicly by IP with durable data and scheduled work.
Architecture: Nginx static frontend and API proxy; Docker Python 3.12 API/scheduler and MySQL 8.4. Bind database to loopback port 9999, API to loopback 8000; serve frontend on 80 and 9998.
Spec: user request to clear previous projects, deploy without benchu.xyz.

- [x] Stop old MySQL, archive old application/database/configuration/PM2 state, verify archive, then remove old application files and disable old service.
- [x] Add deployment Dockerfile, compose and nginx configuration; validate build and configuration.
- [x] Back up local lottery database and artifacts; restore on server; compare counts and preserve prediction artifacts.
- [x] Disable local scheduler; enable cloud scheduler only after database import.
- [x] Verify API, frontend, public access, restart persistence and document operations.

Review focus: duplicate notifications, secret exposure, archive integrity, artifact paths, cloud source accessibility.

Evidence: 39 backend tests and production-image tests passed; frontend production build passed; old archive SHA256 verified; HTTP port 80 returns 200. Docker Hub is unreachable from the server, so official amd64 images are built/downloaded locally and transferred over verified SSH.

Final verification: cloud sync sporttery/CWL/Shanghai succeeded; imported 2938 DLT + 3518 SSQ draws; prediction IDs 1/2 replay and snapshot hashes passed. Public root/health/draws/predictions/tasks HTTP 200. After API/scheduler restart, data counts and scheduler heartbeat passed. All three containers use unless-stopped and Docker/Nginx are boot-enabled. Local scheduler ownership guard passed; no local scheduler process was running. Backup created at /opt/lottery/backups/20261023T095330Z. Independent configuration review found no important issues. Public 9998 remains blocked by security group; public 80 is verified. Browser automation timed out, so browser rendering itself was not revalidated in this deployment.
