# Friday Production Readiness

Use this checklist before treating Friday as production-ready on a real machine or cloud deployment.

## Local hardening

- Run `python scripts/validate_repo.py`.
- Run `python -m compileall -q core tools input output jarvis.py scripts`.
- Run `python scripts/run_tests.py smoke`.
- Run `python scripts/run_tests.py fast`.
- Run `npm --workspace apps/web run build`.
- Confirm `.env` is ignored and `.env.example` contains placeholders only.
- Confirm `git status --short --ignored` does not show secrets, SQLite stores, model binaries, or build output as tracked candidates.
- Confirm `FRIDAY_AUTONOMY_MODE` and `FRIDAY_AUTONOMY_TRUSTED_ROOTS` match the machine you want Friday to work on. Full autonomy only auto-approves trusted project scopes; hard-stop actions still ask.

## Provider readiness

- Web search: set at least one of `BRAVE_SEARCH_API_KEY`, `GOOGLE_SEARCH_API_KEY` plus `GOOGLE_SEARCH_CX`, `TAVILY_API_KEY`, or `SERPAPI_API_KEY`.
- Text-to-3D: set `MESHY_API_KEY`, `TRIPO_API_KEY`, or configure `text_to_3d_local_command`.
- Photoreal 3D: install Blender and set `model_3d_blender_path` if it is not on PATH.
- Image generation: run local Stable Diffusion at `STABLE_DIFFUSION_URL`, set Hugging Face image credentials, or explicitly use Pollinations.
- Google Workspace: set OAuth client credentials and complete the consent flow.
- Local/API status: verify `/providers/readiness`, `/search/status`, `/images/status`, `/models/3d/status`, and `/text-to-3d/status`.

## Cloud deployment

- Choose Render, Railway, or another host.
- Deploy the API with `deploy/Dockerfile.api`; it installs `requirements-api.txt` instead of the full local desktop/voice stack.
- Set `JARVIS_API_PASSWORD` and a strong `JARVIS_API_SECRET` in the platform secret store.
- Set `FRIDAY_API_CORS_ORIGINS` on the API service to the exact web dashboard origin, such as `https://your-app.vercel.app`.
- Set `FRIDAY_AUTONOMY_MODE=full` only on deployments where background workers should act without babysitting inside configured trusted roots.
- Set `NEXT_PUBLIC_FRIDAY_API_URL` on the web app before building it, because Next.js bakes public env vars into the browser bundle.
- Set only provider keys needed by the deployment. Do not upload local `.env`.
- Configure `DATABASE_URL` and enable `cloud_sync_enabled` only after a real PostgreSQL database is ready.
- Verify `/health` over HTTPS.
- Verify login, refresh token behavior, `/dashboard/snapshot`, `/search/status`, and `/ws/tasks`.
- Run `python scripts/verify_production.py --url https://your-api-host` with `JARVIS_API_PASSWORD` set locally.
- Run a backup/restore drill for SQLite stores and cloud PostgreSQL sync data.

## GitHub baseline

- Keep generated folders, `.env`, data stores, model binaries, and build output ignored.
- Require the `Friday CI` workflow before merging.
- Keep provider keys in GitHub Actions secrets, never in repository files.
