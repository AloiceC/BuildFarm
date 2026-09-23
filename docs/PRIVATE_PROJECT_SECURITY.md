# BuildFarm v1 — Private project security model

BuildFarm is public. Any workflow that builds a private project must assume that workflow files, run metadata, normal Actions logs, and BuildFarm artifacts are public.

This document is the unified v1 contract. Private projects should reuse the same source-handoff/build boundary. Authentication/result backends may differ only when documented by the project adapter.

## Source handoff

Each private project uses the private-repository branch:

```text
ci/buildfarm
```

At runtime BuildFarm resolves that ref to one exact commit SHA. Reproducibility/debugging may supply a full exact SHA directly.

Do not accept arbitrary repository names from workflow input. Every public project adapter hard-codes its allowed source repository.

## Private repository credentials

### Preferred GitHub App backend

A dedicated project-scoped GitHub App remains the preferred backend when it can be installed reliably.

Typical repository permissions:

- Metadata: read
- Contents: read
- Checks: write

Do not grant Contents write, Actions write, Administration, or broad account-wide repository access.

The private key lives only in BuildFarm Actions secrets. It is never committed.

Source installation tokens are short-lived and are revoked immediately after source acquisition. Result reporting uses a fresh minimum-scope token and revokes it after writing the Check Run.

### Fine-grained PAT fallback

When GitHub App installation is not viable, a project may use a repository-restricted fine-grained PAT as a documented fallback.

For the Pixiv Lite App PAT path the token is restricted to `AloiceC/pixiv-lite-app` and needs only:

- Contents: read
- Commit statuses: read and write

A fine-grained PAT is long-lived and cannot be revoked per workflow run. Therefore BuildFarm must inject it only into the source-acquisition step and the final result-status step. The private build/test command step must not receive the PAT in its environment.

Rotate or delete the PAT when it is exposed, no longer required, or superseded.

## Source credential lifecycle

1. Resolve `ci/buildfarm` (or an explicit full SHA) to the exact commit SHA.
2. If a platform build/delivery task is requested, verify that `BuildFarm / check` is already successful on the same exact SHA using the project's configured result backend.
3. Download that SHA through the GitHub archive API into the hosted runner temporary workspace.
4. Extract the archive without copying Git history.
5. For GitHub App integrations, revoke the source token immediately.
6. For fine-grained PAT integrations, remove the token from the source helper process and rely on step-scoped secret injection; later build/test steps receive no source credential.

BuildFarm must not use `actions/checkout` against the private project repository.

## Result reporting

GitHub App integrations write a private Check Run, which may include sanitized diagnostic text.

Fine-grained PAT fallback integrations write a Commit Status such as `BuildFarm / check`. Commit Status supports only a short description and target URL; it cannot carry the full sanitized diagnostic body available to a Check Run.

Result credentials must be scoped only to the result-writing step. Public BuildFarm logs must never print token values.

## Public log boundary

Private-source commands must not stream stdout/stderr directly into BuildFarm's public Actions log.

Public logs may contain only safe operational summaries such as:

- project id;
- resolved exact SHA;
- stage name;
- PASS / FAIL;
- duration;
- selected trusted mirror/fallback;
- binary/ciphertext size and SHA-256.

Private compiler output, source snippets, test source excerpts, credentials, private absolute paths, and full stack traces must stay out of the public log.

Runner-local logs are sanitized before any failure detail is sent to a backend that supports private diagnostic text. At minimum, sanitization must remove source excerpts, absolute source-root paths, obvious credential/token forms, ANSI control sequences, and unbounded lines/output.

## Build/check separation

The platform-independent `check` task is run once per exact SHA.

Platform build and delivery tasks require a successful private `BuildFarm / check` result on that same SHA; they must not repeat analyze/test merely because a Windows or Android build is requested. The gate may read a Check Run or Commit Status according to the project's configured backend.

Use `concurrency` + `cancel-in-progress` so a newer task supersedes an older task of the same project/task class.

Do not high-frequency retry CI. Read the available private result metadata, make a concrete source/config change, move `ci/buildfarm` when appropriate, then run again.

## Binary policy

### Normal CI build

A normal private-project Windows/Android build is verification only:

1. build the binary;
2. calculate safe size/SHA-256 metadata;
3. delete the raw package from the runner;
4. do not upload APK/EXE/ZIP as a BuildFarm artifact.

### User delivery build

When the owner needs a package for real testing:

1. build the package;
2. encrypt it with the owner's age public recipient;
3. delete the raw package;
4. upload only the `.age` ciphertext through `actions/upload-artifact`;
5. keep the age private key only on the owner's local machine.

Self-hosted runners are not part of the BuildFarm v1 delivery design.

## Project/build ownership

The private project repository remains the only source of truth for:

- lockfiles;
- project/toolchain versions;
- private build manifest;
- project-specific compatibility lessons;
- architecture and roadmap;
- private project history/status.

BuildFarm contains only reusable public infrastructure and a thin public-safe adapter for each project.

## Mirrors

Prefer trusted and verifiable China mirrors when available and useful. Probe/fallback to official sources where practical. Never use unknown GitHub accelerators or opaque third-party download proxies just for speed.

The current approved public examples include CFUG Flutter/Pub mirrors and an explicitly probed Aliyun Gradle distribution mirror. Android SDK packages stay on Google's official infrastructure unless an equally trustworthy/verifiable alternative is deliberately approved.
