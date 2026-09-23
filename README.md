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

All private projects use one unified source-handoff/build pattern, while the repository credential backend may differ by project:

1. The private repository exposes the handoff ref `ci/buildfarm`.
2. BuildFarm resolves that ref to an exact commit SHA before building.
3. Prefer a dedicated project-scoped GitHub App with only the required repository permissions. Where GitHub App installation is not viable, a repository-restricted fine-grained PAT may be used as a documented fallback.
4. BuildFarm downloads the exact SHA through GitHub's archive API; it does **not** use `actions/checkout` against the private repository and does not copy Git history.
5. GitHub App source tokens are revoked immediately after source acquisition. Fine-grained PATs are long-lived, so they are exposed only to the specific source/result steps and never to private build commands.
6. Private-source stdout/stderr stays out of public BuildFarm logs.
7. Results are written back to the exact private commit using the project's configured backend: Check Run for GitHub App integrations or Commit Status for PAT fallback integrations.
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

Pixiv Lite App is the first private Flutter project wired to BuildFarm v1 and currently uses the fine-grained-PAT/Commit-Status fallback path. Celeste Basecamp remains on the GitHub-App/Check-Run Tauri path. MintLink is not yet being validated in this round.
