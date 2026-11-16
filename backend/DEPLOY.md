# Deploying GraphShield (live link)

Submission needs a hosted app, a public repo and a Loom. **Status of this file: untested.** The Docker path was written from
HydraDB's README and your WSL build notes; it has not been built here. Do a cold-start test before relying on it.

## What must be true for a safe public demo
- HydraDB's Bolt port (7687) is never exposed to the internet. Only the API (8800, behind HTTPS) is public.
- `GRAPHSHIELD_ADMIN_TOKEN` is set. Mutation endpoints then require the `x-graphshield-admin` header.
- Only read-only MCP tools run publicly. The write tool stays sandboxed and approval-gated.
- No secrets in the repo (`.env` is ignored).

## Option A: Docker Compose on one VM (cleanest, unverified)
1. Fix the two `ARG` refs in `Dockerfile.hydradb` to match what you built in WSL (`history | grep -i -E "graphblas|lagraph"`).
2. `cp .env.example .env`, then set `HYDRADB_TOKEN` (32+ chars) and `GRAPHSHIELD_ADMIN_TOKEN`.
3. Put the Olist CSVs in `data/olist/` (`python scripts/fetch_olist.py`, then `python scripts/build_refund_cases.py`).
4. `docker compose up -d --build` (first build is long). Check: `docker compose ps` shows hydradb healthy.
5. Seed once:
   `docker compose exec api python -m graphshield.real_mcp discover`
   `docker compose exec api python -m graphshield.real_mcp seed`
   `docker compose exec api python -m graphshield.enterprise_cli diagnostics`
6. Generate the evidence the dashboard shows:
   `docker compose exec api python -m graphshield.refund_online`
   `docker compose exec api python -m graphshield.refund_online --scenario stationary`
7. Put HTTPS in front of port 8800 (Caddy or your platform's proxy) and test from a fresh browser.

## Option B: your proven WSL steps on a Linux VM
Repeat exactly what already worked in WSL (build `graph-node`, start it bound to localhost), run the API with
`uvicorn graphshield.api:app --host 127.0.0.1 --port 8800`, and publish it through a reverse proxy with HTTPS.
Same security rules as above. This is the lower-risk path if the Docker build fights you.

## Cold-start checklist
- [ ] Fresh browser opens the live URL; Refund Desk loads cases
- [ ] A traced case streams steps and shows HydraDB queries
- [ ] Failure injection reroutes; after restarting the API container the route still avoids the failed provider
- [ ] "Load online-learning curve" shows backend = hydradb (no DRY RUN banner)
- [ ] Rate limiting and admin token verified (a POST without the header returns 403)
