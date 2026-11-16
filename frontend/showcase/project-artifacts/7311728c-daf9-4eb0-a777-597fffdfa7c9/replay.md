# Replay this Real Project Mode evaluation

- Evaluation: `7311728c-daf9-4eb0-a777-597fffdfa7c9`
- Adapter: `node-redis-compose-v1` version `1.0.0`
- Source: https://github.com/dockersamples/nginx-node-redis at `2cd75d3b61385ab4cd490af9d0facc5d8595bca7`
- Mode: `quick`

## API replay

```powershell
$body = @{ inspection_id = "842c194d-b318-4549-b035-6e50804412f7"; adapter_id = "node-redis-compose-v1"; mode = "quick"; challenge = "faster"; consent = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post -ContentType application/json -Body $body
```

The source is fetched read-only at the pinned commit. DARWIN never edits, commits or pushes it.

## Candidate diff

```diff
--- a/darwin-owned-compose.yaml
+++ b/darwin-owned-compose.yaml
@@ DARWIN generates this file; the repository Compose file is never used @@
+ replicas-2x1: replicas=2 workers=1

```
