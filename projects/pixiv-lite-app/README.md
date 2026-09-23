# Pixiv Lite App on BuildFarm

Source repository: `AloiceC/pixiv-lite-app` (private)

This directory contains only the thin public adapter required by BuildFarm v1. It does not contain Pixiv Lite App source, private assets, project history, tokens, signing material, or private build diagnostics.

## Handoff

Normal input is the private repository ref:

```text
ci/buildfarm
```

BuildFarm resolves that ref to an exact commit SHA before source download. An explicit full SHA may be supplied for reproducibility/debugging.

## GitHub App

Pixiv Lite App uses a dedicated project-scoped GitHub App.

Required repository permissions:

- Metadata: read
- Contents: read
- Checks: write

BuildFarm configuration expected by `.github/workflows/pixiv-lite-app.yml`:

- repository variable `PIXIV_LITE_APP_CLIENT_ID`
- repository secret `PIXIV_LITE_APP_PRIVATE_KEY`

The App should be installed only on the repositories it actually needs; for the first integration that is `AloiceC/pixiv-lite-app` only.

## Private source and diagnostics

The reusable BuildFarm v1 workflow downloads an exact GitHub archive snapshot. It does not run `actions/checkout` against the private repository and does not copy Git history.

Private source command stdout/stderr is captured to runner-local files. The public BuildFarm console receives only stage summaries, exact SHA, status, duration, and safe hashes/sizes.

Sanitized failure diagnostics are written back to the corresponding private commit via GitHub Check Runs.

## Binary delivery

Normal Windows/Android build verification discards the raw package after hashing it.

`deliver-windows` and `deliver-android` require an age public recipient in the private project's `ci/buildfarm.toml`. Only the `.age` ciphertext is uploaded as a BuildFarm artifact. The age private key stays local to the project owner.

Project-specific toolchain versions and compatibility history are intentionally not duplicated here. Read them from the private project's manifest/docs after source handoff.
