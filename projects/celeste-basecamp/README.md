# Celeste Basecamp on BuildFarm

Source repository: `AloiceC/Celeste-Basecamp` (private)

This directory is a thin public-safe BuildFarm v1 adapter. It does not contain Celeste Basecamp source, project history, private assets, credentials, private diagnostics, lockfiles, or project-owned build configuration.

## Handoff

Normal input is the private repository ref:

```text
ci/buildfarm
```

BuildFarm resolves that ref to an exact commit SHA before source download. An explicit full SHA may be supplied for reproducibility/debugging.

## GitHub App

Celeste Basecamp uses one dedicated project-scoped GitHub App installed only on `AloiceC/Celeste-Basecamp` for the first integration.

Required repository permissions:

- Metadata: read
- Contents: read
- Checks: write

BuildFarm configuration expected by `.github/workflows/celeste-basecamp.yml`:

- repository variable `CELESTE_BASECAMP_CLIENT_ID`
- repository secret `CELESTE_BASECAMP_PRIVATE_KEY`

No Contents write, Actions write, or Administration permission is required.

## Shared v1 security lifecycle

The Tauri workflow reuses BuildFarm's existing `scripts/private-ci` lifecycle:

- `read_adapter.py` reads this public adapter;
- `fetch_private_source.py` resolves `ci/buildfarm`, downloads the exact SHA archive, and revokes the source token before private commands run;
- `post_private_check.py` writes sanitized diagnostics back to the private commit using a fresh short-lived result token;
- `finalize.py` makes private Check Run reporting part of task success;
- `cleanup.py` removes private source and runner-local diagnostics;
- `install_age.py` provides age only for explicit delivery tasks.

Private source is never fetched with `actions/checkout` and Git history is never copied into BuildFarm.

## Tasks

The manual entry workflow exposes:

- `check` — project-defined frontend/Rust validation on `windows-latest`;
- `build-windows` — requires a green `BuildFarm / check` on the same exact SHA, performs only the Windows build preparation/build path, records safe binary metadata, and discards raw private output;
- `deliver-windows` — same SHA gate, then age-encrypts the project-declared acceptance package and uploads only the `.age` ciphertext.

The private repository's `.buildfarm/project.json` remains authoritative for Node/pnpm/Rust/Tauri commands and delivery file paths. BuildFarm does not duplicate those versions here.

## Delivery

Set `age_recipient` in this public-safe adapter before the first `deliver-windows` run. The age private key remains local to the owner and never enters BuildFarm.
