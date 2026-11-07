# Quickstart — Feature 036

All commands run from the repository root `1/` with the workspace venv. Python processes
must be able to write; set `TEMP`/`TMP` inside the repo if the default temp dir is not
writable.

## 1. Gates

```powershell
.venv/Scripts/python.exe -m pytest apps/specops/tests/test_lab_engine.py apps/specops/tests/test_specops_lab_router.py -q
.venv/Scripts/python.exe -m pytest apps/specops/tests -q
```

The engine suite proves: malformed roster refused, unsupported asset scheme refused, launch refused
without RoE, external targets accepted under RoE, funnel derived from engagement events, capture encrypted/redacted/audited,
retention purge keeps counts, kill switch stops sessions, teardown preserves evidence,
report figures are null with named instrumentation when unavailable.

The router suite proves the same through FastAPI: `409` authorization, `422` target,
`424` setup, cross-tenant `404`, no raw secret in any JSON body.

## 2. Phishing Club service

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile phishingclub up -d phishingclub
Invoke-RestMethod http://127.0.0.1:8000/api/v1/specops/lab/phishingclub/health
```

The release image publishes the admin console on `https://127.0.0.1:8002`, phishing HTTP
on `18080`, and phishing HTTPS on `18443`. The first start prints one-time admin
credentials in `docker logs cognitive-dev-phishingclub-1`. The adapter accepts the
self-signed loopback certificate by default; set `PHISHINGCLUB_VERIFY_TLS=true` for a
remote service.

## 3. UI

```powershell
cd apps/webapp
npm test -- --run src/lab/LabCanvas.test.tsx
npm run build
npm run lint
```

Open `http://127.0.0.1:5173/specops/lab`. The persistent banner must read
`full red-team · RoE-gated · Phishing Club`. The Lab Control panel shows the verified
donor and links the local Phishing Club console at `https://127.0.0.1:8002`.

## 4. Manual API walk (dev server)

```powershell
$base = "http://127.0.0.1:8000/api/v1"
# Record a sign-off (dev auth headers required by the running control plane)
$roe = Invoke-RestMethod -Method Post "$base/specops/roe" -ContentType application/json -Body (@{
  target_ref = "external.example"; scope = "red-team drill"; approved_by = "supervisor"
} | ConvertTo-Json)
# Create a lab campaign
$c = Invoke-RestMethod -Method Post "$base/specops/lab/campaigns" -ContentType application/json -Body (@{
  name = "Q4 drill"; template_id = "tpl-lure"; roster = @("alice@external.example", "bob@external.example")
} | ConvertTo-Json)
# Launch
Invoke-RestMethod -Method Post "$base/specops/lab/campaigns/$($c.campaign.campaign_id)/launch" `
  -ContentType application/json -Body (@{ roe_id = $roe.roe_id } | ConvertTo-Json)
# Start an AiTM session and capture a synthetic artifact
$s = Invoke-RestMethod -Method Post "$base/specops/lab/aitm/sessions" -ContentType application/json -Body (@{
  mode = "reverse_proxy"; target_host = "external.example"; roe_id = $roe.roe_id
} | ConvertTo-Json)
Invoke-RestMethod -Method Post "$base/specops/lab/aitm/sessions/$($s.session.session_id)/capture" `
  -ContentType application/json -Body (@{ kind = "token"; secret = "synthetic-token"; label = "session" } | ConvertTo-Json)
# Kill switch
Invoke-RestMethod -Method Post "$base/specops/lab/kill-switch"
```

Assert: the capture response has only a redacted preview; `GET /specops/lab/audit`
contains `artifact.captured`, `campaign.launched`, `lab.kill_switch`; the report never
contains `synthetic-token`.

## 5. Platform model drift

```powershell
.venv/Scripts/python.exe -m platform_model.build
.venv/Scripts/python.exe -m platform_model.build --check
```

## 6. Rollback

Disable the department by removing the nav entry/route (or the router mount), or stop
the optional `phishingclub` compose profile. Neither action deletes evidence.
