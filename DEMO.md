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

The clone is based on `UBC-FRESH/fhops` `main` at the P20 merge. The demo wrapper adds only the landing page, `/demo` alias, and `/sandbox` static mount. The optional agent is enabled for the public demo. App-level rate and body-size limits remain active.

Nginx should reverse-proxy the public root to `http://127.0.0.1:8780`.

The fancy Tree Lab sandbox is served at `/sandbox/` (not the old static viewer).
App-level public-demo limits: 300 requests/minute per client and 64 KiB request
body cap. Nginx should add its own edge rate/size limits.
