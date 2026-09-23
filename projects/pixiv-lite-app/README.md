# Pixiv Lite App on BuildFarm

Source repository: `AloiceC/pixiv-lite-app` (private)

This directory contains only the thin public adapter required by BuildFarm v1. It does not contain Pixiv Lite App source, private assets, project history, tokens, signing material, or private build diagnostics.

## Handoff

Normal input is the private repository ref:

```text
ci/buildfarm
```

BuildFarm resolves that ref to an exact commit SHA before source download. An explicit full SHA may be supplied for reproducibility/debugging.

## Fine-grained PAT authentication

Pixiv Lite App uses a project-scoped fine-grained personal access token because GitHub App installation could not be completed reliably for this account.

The token must be restricted to `AloiceC/pixiv-lite-app` only and needs only:

- Contents: read
- Commit statuses: read and write

BuildFarm configuration expected by `.github/workflows/pixiv-lite-app.yml`:

- repository secret `PIXIV_LITE_APP_TOKEN`

The token is long-lived and therefore cannot be revoked after each run like a GitHub App installation token. BuildFarm limits exposure instead: the PAT is injected only into the source-acquisition step and the final commit-status step. Private build/test commands receive no repository credential. Rotate the token manually if it is exposed or no longer needed.

The older `PIXIV_LITE_APP_CLIENT_ID` and `PIXIV_LITE_APP_PRIVATE_KEY` settings are not used by the PAT path and may be removed after the PAT-backed CI path is validated.

## Private source and result reporting

The reusable BuildFarm v1 workflow downloads an exact GitHub archive snapshot. It does not run `actions/checkout` against the private repository and does not copy Git history.

Private source command stdout/stderr is captured to runner-local files. The public BuildFarm console receives only stage summaries, exact SHA, status, duration, and safe hashes/sizes.

PAT-backed runs write the final result to the exact private commit using a Commit Status such as `BuildFarm / check`. Commit Status supports only a short description and target URL, so full sanitized diagnostics are not attached to the private commit. Runner-local diagnostics are still removed during cleanup.

## Binary delivery

Normal Windows/Android build verification discards the raw package after hashing it.

`deliver-windows` and `deliver-android` read the owner's age public recipient from the public-safe `adapter.toml`. Only the `.age` ciphertext is uploaded as a BuildFarm artifact. The age private key stays local to the project owner.

Keeping the public recipient in the adapter means rotating it does not move the private `ci/buildfarm` source handoff or invalidate an already-green `BuildFarm / check` on that SHA.

Project-specific toolchain versions and compatibility history are intentionally not duplicated here. Read them from the private project's manifest/docs after source handoff.
