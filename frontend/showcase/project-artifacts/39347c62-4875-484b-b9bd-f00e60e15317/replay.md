# Replay this simulated architecture screening

- Evaluation: `39347c62-4875-484b-b9bd-f00e60e15317`
- Adapter: `architecture-screening-v1` version `1.0.0`
- Source: https://github.com/example/AGENTBLAZER at `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
- Mode: `full`
- Evidence kind: `simulated`
- Recommendation: `IMPROVEMENT_CANDIDATE`

## API replay

```powershell
$body = @{ inspection_id = "5c006716-f637-4c23-ac9d-6b5fcbc293fe"; adapter_id = "architecture-screening-v1"; mode = "full"; consent = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post -ContentType application/json -Body $body
```

## What ran

The deterministic `architecture-screening-v1` model read the architecture recorded in `architecture.json` and evaluated deployment-level controls. No repository code, dependency, package manager, container or service was started. The source checkout was never edited, committed or pushed.

## Important

The recommendation is SIMULATED and NOT_MEASURED. It is an uncalibrated candidate for real deployment validation, not a measured winner.
