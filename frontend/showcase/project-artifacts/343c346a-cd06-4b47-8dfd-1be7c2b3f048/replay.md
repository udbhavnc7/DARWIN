# Replay this simulated architecture screening

- Evaluation: `343c346a-cd06-4b47-8dfd-1be7c2b3f048`
- Adapter: `architecture-screening-v1` version `1.0.0`
- Source: https://github.com/udbhavnc7/TATTAVA at `cb21876d5c481ccddb6fbb5d09c7569d11b80c94`
- Mode: `full`
- Evidence kind: `simulated`
- Recommendation: `IMPROVEMENT_CANDIDATE`

## API replay

```powershell
$body = @{ inspection_id = "f3ce9e22-509e-45ed-a8e8-2d8b70397475"; adapter_id = "architecture-screening-v1"; mode = "full"; consent = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post -ContentType application/json -Body $body
```

## What ran

The deterministic `architecture-screening-v1` model read the architecture recorded in `architecture.json` and evaluated deployment-level controls. No repository code, dependency, package manager, container or service was started. The source checkout was never edited, committed or pushed.

## Important

The recommendation is SIMULATED and NOT_MEASURED. It is an uncalibrated candidate for real deployment validation, not a measured winner.
