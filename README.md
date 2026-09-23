# BuildFarm

Shared public CI/build infrastructure for AloiceC projects.

## Purpose

BuildFarm exists to host reusable GitHub Actions workflows, build scripts, compatibility notes, and other **public-safe CI infrastructure**. Standard GitHub-hosted runners may be used here so public-repository CI does not consume private-repository hosted-runner minutes.

BuildFarm is **not** a second product source repository. Each project's own repository remains the source of truth for product code, architecture, roadmap, and project-specific status.

## Security boundary

Do **not** commit or copy any of the following into BuildFarm unless the project owner explicitly decides that material is public:

- private project source code;
- proprietary/private assets;
- signing keys or certificates;
- access tokens, credentials, passwords, or private URLs;
- user data;
- private project notes/history that are not meant to be published.

A project that remains private must have an explicitly designed source handoff before BuildFarm is allowed to build it. Do not solve private-CI quota issues by casually mirroring the private repository into this public one.

## Shared CI rules

1. Prefer mature, existing CI implementations and official/reputable actions over custom bootstrap code.
2. Prefer trusted and verifiable China mirrors when they materially improve download speed. Keep official sources as fallback where practical. Never use unknown GitHub accelerators just for speed.
3. Pin important toolchain versions when compatibility matters. Do not blindly chase latest package versions.
4. Cache downloads/toolchains where useful, but cache must never be required for correctness.
5. Keep artifacts and caches bounded; public hosted-runner minutes may be free for standard runners, but storage and retention are not unlimited.
6. Avoid high-frequency CI retries. Inspect the failure, make a concrete code/config change, then run again.
7. Keep project-specific compatibility lessons in the project's own repository when they contain private history or design context. BuildFarm should only contain reusable/public-safe conclusions.
8. Before onboarding a project, read this README, inspect existing workflows, and read that project's own CI/build documentation.

## Suggested repository layout

```text
.github/workflows/        # BuildFarm workflows
scripts/                  # reusable public CI helpers
projects/<project>/       # public-safe project-specific build adapters/config
 docs/                    # shared compatibility and CI notes
```

The exact structure may evolve as the first projects are onboarded.

## Current onboarding status

BuildFarm has been created as the replacement direction for projects that were temporarily using local Windows self-hosted runners. The first integration should establish the reusable conventions before additional projects copy them.

For MintLink specifically, consult the private repository's `docs/CI_BUILD_LESSONS.md` before making toolchain or Android 17 CI decisions.
