# BuildFarm

Shared public CI/build infrastructure for AloiceC projects.

## Purpose

BuildFarm hosts reusable GitHub Actions workflows, build scripts, compatibility notes, and other **public-safe CI infrastructure**. Standard GitHub-hosted runners are preferred so project repositories do not need to duplicate heavy CI implementations.

BuildFarm is **not** a second product source repository. Each project's own repository remains the source of truth for product code, architecture, roadmap, lockfiles, toolchain versions, project-specific compatibility lessons, and project status.

## Security boundary

Do **not** commit or copy any of the following into BuildFarm unless the project owner explicitly decides that material is public:

- private project source code;
- proprietary/private assets;
- signing keys or certificates;
- access tokens, credentials, passwords, age private keys, or private URLs;
- user data;
- private project notes/history that are not meant to be published.

See [`docs/PRIVATE_PROJECT_SECURITY.md`](docs/PRIVATE_PROJECT_SECURITY.md) for the BuildFarm v1 private-project contract.

## BuildFarm v1 private-project standard

All private projects use one unified pattern:

1. The private repository exposes the handoff ref `ci/buildfarm`.
2. BuildFarm resolves that ref to an exact commit SHA before building.
3. One dedicated project-scoped GitHub App provides only `Metadata: read + Contents: read + Checks: write`.
4. BuildFarm downloads the exact SHA through GitHub's archive API; it does **not** use `actions/checkout` against the private repository and does not copy Git history.
5. The source token is revoked immediately after source acquisition.
6. Private-source stdout/stderr stays out of public BuildFarm logs.
7. Sanitized failure diagnostics are written back to the private commit as a Check Run using a newly generated short-lived token.
8. Normal private binaries are hashed then discarded; raw APK/EXE/ZIP files are not uploaded publicly.
9. Test-delivery packages are encrypted with the owner's age public recipient and only the `.age` ciphertext is uploaded as a public artifact.
10. Self-hosted runners are not part of the v1 delivery model.

BuildFarm project directories are intentionally thin adapters. Project toolchain versions, build manifests, lockfiles, and project-specific compatibility history stay private.

## Shared CI rules

1. Prefer mature, existing CI implementations and official/reputable actions over custom bootstrap code.
2. Prefer trusted and verifiable China mirrors when they materially improve download speed. Keep official sources as fallback where practical. Never use unknown GitHub accelerators just for speed.
3. Pin important toolchain versions when compatibility matters. Do not blindly chase latest package versions.
4. Cache downloads/toolchains where useful, but cache must never be required for correctness.
5. Keep artifacts and caches bounded.
6. Avoid high-frequency CI retries. Inspect the failure, make a concrete code/config change, then run again.
7. Keep project-specific compatibility lessons in the project's own repository when they contain private history or design context. BuildFarm should only contain reusable/public-safe conclusions.
8. Before onboarding a project, read this README, inspect existing workflows, and read that project's own CI/build documentation.
9. Platform-independent checks should run once per exact SHA; platform builds must not repeat them unnecessarily.
10. Use `concurrency` + `cancel-in-progress` for superseded jobs.

## Repository layout

```text
.github/workflows/        # public entry/reusable workflows
scripts/private-ci/       # reusable BuildFarm v1 private-project helpers
projects/<project>/       # thin public-safe project adapter
 docs/                    # shared compatibility and CI notes
```

## Current onboarding status

Pixiv Lite App is the first project wired to the unified BuildFarm v1 private-project path. MintLink and future private projects should reuse the same source-token/archive/check-run/age-delivery conventions rather than creating project-specific alternatives.
