# BuildFarm

Shared public CI/build infrastructure for AloiceC projects.

## Purpose

BuildFarm exists to host reusable GitHub Actions workflows, build scripts, compatibility notes, and other **public-safe CI infrastructure**. Standard GitHub-hosted runners may be used here so public-repository CI does not consume private-repository hosted-runner minutes.

BuildFarm is **not** a second product source repository. Each project's own repository remains the source of truth for product code, architecture, roadmap, project-specific status, lockfiles, toolchain versions, and build manifests.

## Security boundary

Do **not** commit or copy any of the following into BuildFarm unless the project owner explicitly decides that material is public:

- private project source code;
- proprietary/private assets;
- signing keys or certificates;
- access tokens, credentials, passwords, or private URLs;
- user data;
- private project notes/history that are not meant to be published.

A project that remains private must use the BuildFarm v1 private-project contract in `docs/PRIVATE_PROJECT_SECURITY.md`. Do not solve private-CI quota issues by mirroring the private repository into this public one.

## Shared CI rules

1. Prefer mature, existing CI implementations and official/reputable actions over custom bootstrap code.
2. Prefer trusted and verifiable China mirrors when they materially improve download speed. Keep official sources as fallback where practical. Never use unknown GitHub accelerators just for speed.
3. Pin important toolchain versions when compatibility matters. Project-specific pins belong to the project repository.
4. Cache downloads/toolchains where useful, but cache must never be required for correctness.
5. Keep artifacts and caches bounded; public hosted-runner minutes may be free for standard runners, but storage and retention are not unlimited.
6. Avoid high-frequency CI retries. Inspect the failure, make a concrete code/config change, then run again.
7. Keep project-specific compatibility lessons in the project's own repository when they contain private history or design context. BuildFarm should only contain reusable/public-safe conclusions.
8. Before onboarding a project, read this README, inspect existing BuildFarm workflows, and read that project's own CI/build documentation.

## Repository layout

```text
.github/workflows/        # shared/public BuildFarm workflows
scripts/                  # reusable public CI helpers
projects/<project>/       # thin public-safe project adapters
docs/                     # shared compatibility/security notes
```

## Private projects — v1

Private projects use one shared pattern:

`private ci/buildfarm ref -> exact SHA -> dedicated GitHub App token -> GitHub archive API -> runner temp -> token revoke -> suppressed private validation -> private Check Run`

Normal private validation uploads no raw private build output. Acceptance packages are uploaded only after age public-key encryption.

The shared implementation is `.github/workflows/private-project-v1.yml` plus `scripts/private-project/*`. Project-specific toolchain and build commands are read at runtime from the private repository's own BuildFarm manifest.

## Current onboarding status

- MintLink has a public Flutter/Android toolchain smoke and is being aligned to the v1 private-project contract.
- Celeste Basecamp is the first Windows/Tauri project adapter for the shared private-project v1 workflow.

For MintLink-specific Android compatibility history, consult the private repository's `docs/CI_BUILD_LESSONS.md`.
