# FHOPS public demo

Stable container-local service:

- Host: `127.0.0.1`
- Port: `8780`
- Landing: `/`
- Serious game: `/game`
- 3D Tree Lab sandbox: `/sandbox/`
- Health: `/api/health`

Start/restart:

```bash
cd /home/gep/projects/fhops-public-demo
./run_public_demo.sh
```

Supervised operation:

```bash
cd /home/gep/projects/fhops-public-demo
scripts/start_public_demo_supervisor.sh
scripts/public_demo_health.sh
```

The supervisor runs in a detached tmux session, checks
`http://127.0.0.1:8780/studio/api/health` every 5 seconds, and restarts uvicorn
if the origin is down. A user crontab entry recreates the tmux supervisor every
minute and after reboot.

The clone is based on `UBC-FRESH/fhops` `main` at the P20 merge. The demo wrapper adds only the landing page, `/demo` alias, and `/sandbox` static mount. The optional agent is enabled for the public demo. App-level rate and body-size limits remain active.

Nginx should reverse-proxy the public root to `http://127.0.0.1:8780`.

The fancy Tree Lab sandbox is served at `/sandbox/` (not the old static viewer).
App-level public-demo limits: 300 requests/minute per client and 64 KiB request
body cap. Nginx should add its own edge rate/size limits.
