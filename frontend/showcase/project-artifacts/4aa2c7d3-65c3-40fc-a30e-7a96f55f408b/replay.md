# Replay this simulated architecture screening

- Evaluation: `4aa2c7d3-65c3-40fc-a30e-7a96f55f408b`
- Adapter: `architecture-screening-v1` version `1.0.0`
- Source: https://github.com/udbhavnc7/SAATHI at `b1a306388f4595a3daa5c33b8573c80191c5e8dc`
- Mode: `full`
- Evidence kind: `simulated`
- Recommendation: `IMPROVEMENT_CANDIDATE`

## API replay

```powershell
$body = @{ inspection_id = "29366cfd-d626-4015-98ff-3856cc6dddd7"; adapter_id = "architecture-screening-v1"; mode = "full"; consent = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post -ContentType application/json -Body $body
```

## What ran

The deterministic `architecture-screening-v1` model read the architecture recorded in `architecture.json` and evaluated deployment-level controls. No repository code, dependency, package manager, container or service was started. The source checkout was never edited, committed or pushed.

## Important

The recommendation is SIMULATED and NOT_MEASURED. It is an uncalibrated candidate for real deployment validation, not a measured winner.
