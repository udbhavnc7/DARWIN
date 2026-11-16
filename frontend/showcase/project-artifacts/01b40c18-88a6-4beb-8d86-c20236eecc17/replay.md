# Replay this Real Project Mode evaluation

- Evaluation: `01b40c18-88a6-4beb-8d86-c20236eecc17`
- Adapter: `flask-redis-compose-v1` version `1.0.0`
- Source: https://github.com/docker/awesome-compose at `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`
- Mode: `quick`

## API replay

```powershell
$body = @{ inspection_id = "8c4e7902-5475-44dc-a702-158bffb765d8"; adapter_id = "flask-redis-compose-v1"; mode = "quick"; challenge = "faster"; consent = $true } | ConvertTo-Json
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
