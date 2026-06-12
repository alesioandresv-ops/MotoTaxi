Railway deployment checklist for MotoTaxi

1) Backend service settings
- In Railway, open your backend service settings → Environment Variables.
- Add or verify:
  - `NODE_ENV=production`
  - `ENFORCE_HTTPS=true`
  - `PORT` — leave unset so Railway assigns the port, or set to Railway's provided port variable if required.
  - Database variables (`MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT`) must be set if using MySQL.

2) Frontend options
- If you deploy frontend as a separate Railway service, set its `REACT_APP_API_URL` to the backend's HTTPS URL (for example `https://mototaxi-production.up.railway.app`). Then redeploy frontend so the `build` includes that env value.
- If you serve the frontend `build` from the backend (recommended), ensure frontend `build` step runs during backend install (your `backend/package.json` already runs the build in `install`). In that case leave `REACT_APP_API_URL` empty so client uses relative `/api` paths.

3) Redeploy
- Trigger a redeploy on Railway for both services (or the single backend service if serving build), and wait for the build logs to finish.

4) Verify
- Open the site: https://mototaxi-production.up.railway.app
- Check health endpoint: https://mototaxi-production.up.railway.app/api/health
- Try registering a user via the frontend UI and confirm no mixed-content errors in browser devtools console.

5) Troubleshooting
- If the browser blocks requests due to mixed-content, rebuild frontend so `REACT_APP_API_URL` is HTTPS or empty (relative).
- Check Railway logs for build-time environment variables; the `build` must see the correct `REACT_APP_API_URL` when using a separate frontend service.
- Ensure `ENFORCE_HTTPS=true` is set so backend redirects HTTP to HTTPS (the app uses `trust proxy` to detect forwarded proto).

If you want, I can also:
- Prepare a branch/commit with `frontend/.env` set to the Railway URL (already done),
- Or change it back to empty if you prefer serving build from backend; tell me which option you want to finalize and I will adjust files accordingly.
