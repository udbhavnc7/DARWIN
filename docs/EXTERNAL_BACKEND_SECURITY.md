# External backend security boundary

> Applies to every external repository evaluation in DARWIN.
> Last verified 16 November 2026.

This document states what the current implementation enforces, where each
control lives, and what it does **not** defend. It is written for a reviewer
who has to decide whether it is safe to point DARWIN at a repository.

The governing rule is simple: **a remote repository is untrusted input, not
code to install.** DARWIN may read it, copy a reviewed subset of application
source into its own image, and execute that image only inside an isolated
Linux Docker stack. It never executes the repository's Compose file,
Dockerfile, nginx config, shell scripts, package install hooks or host
interpreter.

---

## 1. Threat model

| Threat | Example | Control |
| --- | --- | --- |
| Malicious build/run instructions | Repository Dockerfile runs `curl … \| sh`, mounts the host, or starts privileged | Repository Compose/Dockerfile are never read into the runner; DARWIN generates its own |
| Host code execution | Importing or measuring runs `app.py`/`server.js` directly on the Windows host | Execution is refused unless a Linux Docker engine is available; there is no host fallback |
| Path traversal / symlink escape | Source entry `../../Users/...` or a symlink to a host file | Relative-path validation before copy, symlinks rejected, resolved path must stay inside the checkout, only basenames are copied |
| Container escape via Docker socket | Generated Compose mounts `/var/run/docker.sock` | Socket paths are forbidden; generated Compose is scanned and refused |
| Privilege escalation | `privileged: true`, added capabilities, host PID/network | Forbidden keys and modes refused; `cap_drop: ALL`, `no-new-privileges`, non-root users |
| Data exfiltration / ingress | App reaches the internet or listens on all interfaces | App and Redis sit on an internal Docker network; only the gateway publishes a port, bound to `127.0.0.1` |
| Resource exhaustion | Fork bomb, memory balloon, CPU spin | Per-service `cpus`, `mem_limit`, `memswap_limit`; bounded load window; explicit cleanup |
| Secret leakage | Repository expects cloud credentials or a payment key | No ambient credentials, no secret mounts, no env passthrough; only `GUNICORN_WORKERS` / `UVICORN_WORKERS` are set |
| Tampered evidence | Edited `benchmark.json` served as proof | Evidence files are allowlisted, registered with SHA-256 and re-verified on read and bundle export |
| Unauthorized local API use | Another local user or a stray page calls the API | Bind `127.0.0.1`; optional `DARWIN_API_TOKEN` also enforced on the websocket |
| SSRF through inspection | User submits an internal URL or non-GitHub host | Inspection accepts public GitHub repository URLs over HTTPS; the importer is not a generic fetcher |

---

## 2. Read-only inspection boundary

Implemented in `backend/darwin/repository_import.py` and
`project_capabilities.py`.

- Only public GitHub repositories are imported, over HTTPS, after explicit
  `consent: true` in the request.
- The requested ref is resolved to an **immutable commit SHA** and recorded.
  Adapters only report `execution_allowed` when the checkout is at the pinned
  reviewed revision.
- Downloads are bounded by file-count and size ceilings; symlinks are not
  followed; the archive is unpacked under the DARWIN cache, not a user path.
- Classification is file-backed. A repository cannot claim support by naming
  itself after an adapter.
- A repository that does not match a reviewed adapter is reported as
  `INSPECTABLE`. DARWIN does not attempt a generic build or run.

Inspection performs no container work and no repository code execution.

---

## 3. Typed, hashed run manifest

`backend/darwin/backend_manifest.py` defines the only description of a run
that the runner accepts. It is written by a reviewed adapter and includes:

- adapter id and version, runtime (`gunicorn-flask`, `uvicorn-fastapi`,
  `node-express` only), app module and port;
- the allowlisted `source_files` (for example `flask-redis/app.py`,
  `flask-redis/requirements.txt`);
- detection markers that must appear in the source before the adapter claims
  support;
- health and workload specs, candidate dimensions and allowed challenges;
- a canonical SHA-256 over all of the above.

`validate_relative_files` rejects empty names, absolute paths, `..`
traversal, drive/URI colons and `~`. The manifest never contains a shell
command, a Compose fragment, an image reference from the repository, or a host
path. `POST /api/repositories/validate-manifest` exposes the same checks
read-only, so a proposed manifest can be reviewed without starting anything.

---

## 4. Isolated runner controls

Implemented in `backend/darwin/isolated_backend.py`.

### 4.1 Preconditions

- `runner_available()` requires the Docker CLI **and** a running Linux Docker
  engine with detectable cgroups. If either is missing, the adapter reports
  `FAILED_INFRASTRUCTURE` with the reason.
- There is deliberately no Windows-host execution path. The host OS runs the
  API; it never runs repository code.

### 4.2 Source copy

- Only files listed in the reviewed manifest are copied.
- Symlinks are refused. The resolved source must remain inside the checkout.
- Files are copied by basename into a fresh build directory, so a crafted
  directory structure cannot influence the image layout.

### 4.3 DARWIN-owned image

| Runtime | Base | Install | User |
| --- | --- | --- | --- |
| `gunicorn-flask` | `python:3.11-alpine` | `pip install -r requirements.txt gunicorn==23.0.0` | `65534:65534` |
| `uvicorn-fastapi` | `python:3.11-alpine` | `pip install -r requirements.txt uvicorn==0.34.0` | `65534:65534` |
| `node-express` | `node:22-alpine` | `npm ci --omit=dev --ignore-scripts` | `65534:65534` |

`--ignore-scripts` prevents npm lifecycle scripts from running at image build
time. The repository's own Dockerfile is not used, so its `USER`, entrypoint,
ports and mounts have no effect.

### 4.4 Compose hardening

Every generated service has:

- `read_only: true` (web and Redis) plus `tmpfs: /tmp` where the process needs
  scratch space;
- `security_opt: ["no-new-privileges:true"]` and `cap_drop: ["ALL"]`;
- a non-root `user` (65534 for app services, 999 for Redis, 101 for nginx);
- CPU and memory limits (`web` 0.5 CPU / 128 MB, Redis and gateway
  0.25 CPU / 64 MB);
- `restart: "no"` so a crash does not create an uncontrolled restart loop.

Network layout:

- `sandbox` is an **internal** Docker network. App replicas and Redis have no
  route to the internet or the host.
- Only the nginx gateway also joins a `host_access` network, because a
  published port requires it. Its only publish is
  `127.0.0.1:<ephemeral> → 8080`; nothing is published on `0.0.0.0`.
- There is no Docker socket mount, no host bind mount except the generated
  read-only `nginx.conf`, and no `privileged`, `devices`, `network_mode: host`
  or `pid: host`.

`assert_safe_compose` scans the generated YAML before writing it and raises
`IsolationError` if a forbidden key, socket fragment or host mode appears.
This is defence in depth: the generator itself never emits those fields, so
the scan catches a future regression.

### 4.5 Lifecycle

- Each candidate gets a uniquely named Compose project (`dwx<random>`); the
  project is torn down after measurement, including on cancellation and on
  adapter error.
- Load is bounded: a fixed warmup and a short measurement window at a fixed
  request rate.
- Fault injection for `recover` restarts one service, not the whole stack, and
  the gateway is probed on loopback.
- Cancellation is cooperative: the evaluation engine marks the run cancelled,
  the adapter checks between phases and returns `AdapterCancelled`, and
  cleanup still runs.

---

## 5. API and evidence boundary

- The API binds `127.0.0.1` only. Do not expose it to a LAN or the internet.
- If `DARWIN_API_TOKEN` is set, HTTP routes and the project websocket both
  require it; the websocket is not an anonymous bypass.
- Evidence is an allowlist: only named files are registered. Each has a
  SHA-256 and byte count; `/artifacts` and `/bundle` verify the digest before
  serving. Unknown names return 404.
- `_`-prefixed internal fields (cache paths, source root, adapter internals)
  are stripped from API responses.
- The evaluation record stores the source URL, pinned SHA, adapter id and
  environment (`isolation: linux-docker`, `repository_compose_used: false`),
  so a reviewer can reconstruct what ran.

---

## 6. Negative tests

These are covered in `tests/test_external_backend.py`:

- unsafe `source_files` (`../outside.py`) is refused by manifest validation;
- a tampered manifest SHA-256 is rejected, and a body that matches its own
  digest but not the reviewed manifest is rejected;
- a non-pinned checkout cannot execute;
- a source missing required markers cannot execute;
- an unsupported repository stays `INSPECTABLE` and cannot start a run;
- a prerequisite failure returns the exact missing prerequisite instead of
  launching;
- a client-pipeline adapter (Sanchay) cannot masquerade as a container
  adapter;
- simulated screening never wins a measured verdict;
- evidence requests for unknown artifact names are refused;
- export of a change document for a non-actionable verdict returns `409`;
- websocket token guard rejects an anonymous connection when a token is set.

The Docker-level assertions (`assert_safe_compose`, socket refusal, loopback
publish) are exercised by the unit tests that build Compose configs; they do
not require a running engine.

---

## 7. Residual risk

This is a local exhibition prototype, not a multi-tenant sandbox service.
Known limits:

- **The Docker daemon is trusted.** Anyone who can talk to the daemon can
  start privileged containers. DARWIN does not harden the daemon. Run it on a
  machine you control.
- **Kernel and container-runtime exploits are out of scope.** A container
  escape is not prevented by Compose flags.
- **Base images are pulled from public registries** (`python:3.11-alpine`,
  `node:22-alpine`, `nginx:1.27-alpine`, `redis:7-alpine`). They are not
  pinned by digest in this increment; supply-chain trust in those images is
  inherited.
- **Build-time egress is allowed.** `pip install` and `npm ci` need registry
  access. Runtime egress is blocked by the internal network, but a malicious
  package could still act at build time. Only reviewed `requirements.txt` /
  `package.json` / lockfile content is copied.
- **No seccomp/AppArmor profile is supplied.** The default runtime profile is
  used.
- **The API is unauthenticated by default.** `DARWIN_API_TOKEN` is optional
  and intended for local use only.
- **No real payment, customer or production data** may be used with these
  targets. The apps are public counter samples; Sanchay is evaluated on
  generated ledgers.
- **A user who can edit the local catalog or manifest code** can change what
  is executed. The reviewed manifest is a code-level control, not a remote
  attestation.

If DARWIN is ever exposed beyond a single trusted operator, these would need
to be addressed first: daemon isolation (rootless or a dedicated VM),
digest-pinned images, egress policy at build time, mandatory API auth, and
per-run audit identity.

---

## 8. Operator checklist

Before a live external run:

1. Confirm the API is on `127.0.0.1` and no proxy intercepts loopback
   (`NO_PROXY=127.0.0.1,localhost`).
2. Confirm the Linux Docker engine is running; otherwise expect inspection
   only and an honest `FAILED_INFRASTRUCTURE` if a run is attempted.
3. Use only the catalogued targets or a repository you are authorised to
   inspect. Do not point this at private or customer repositories.
4. Do not mount personal data, credentials or payment systems into the stack;
   the runner does not, and neither should the operator.
5. After the run, read `environment.json` and the verdict; do not present a
   simulated or recorded result as live.
6. Stop the API and the demo shop when finished. Do not delete or overwrite
   historical evidence.
