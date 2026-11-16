# Replay this Real Project Mode evaluation

- Evaluation: `3017d1c9-5755-4c2d-a7c8-c264f62f1b24`
- Adapter: `flask-redis-compose-v1` version `1.0.0`
- Source: https://github.com/docker/awesome-compose at `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`
- Mode: `full`

## API replay

```powershell
$body = @{ inspection_id = "861ca354-9d00-4a26-afc0-0c6b2d951de9"; adapter_id = "flask-redis-compose-v1"; mode = "full"; challenge = "faster"; consent = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post -ContentType application/json -Body $body
```

The source is fetched read-only at the pinned commit. DARWIN never edits, commits or pushes it.

## Candidate diff

```diff
--- a/darwin-owned-compose.yaml
+++ b/darwin-owned-compose.yaml
@@ DARWIN generates this file; the repository Compose file is never used @@
+ replicas-2x1: replicas=2 workers=1
+ workers-1x2: replicas=1 workers=2

```
