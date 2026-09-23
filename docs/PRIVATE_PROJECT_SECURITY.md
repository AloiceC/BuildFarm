# BuildFarm v1 — Private project security model

BuildFarm is public. Any workflow that builds a private project must assume that workflow files, run metadata, normal Actions logs, and BuildFarm artifacts are public.

This document is the unified v1 contract. Private projects should not invent alternative source-transfer, diagnostic, or delivery mechanisms.

## Source handoff

Each private project uses the private-repository branch:

```text
ci/buildfarm
```

At runtime BuildFarm resolves that ref to one exact commit SHA. Reproducibility/debugging may supply a full exact SHA directly.

Do not accept arbitrary repository names from workflow input. Every public project adapter hard-codes its allowed source repository.

## GitHub App model

Each private project gets one dedicated GitHub App for its first BuildFarm integration.

Required repository permissions only:

- Metadata: read
- Contents: read
- Checks: write

Do not grant Contents write, Actions write, Administration, or broad account-wide repository access.

The private key lives only in BuildFarm Actions secrets. It is never committed.

### Source token lifecycle

1. Create a short-lived GitHub App installation token.
2. Resolve `ci/buildfarm` (or an explicit full SHA) to the exact commit SHA.
3. If a platform build/delivery task is requested, verify that `BuildFarm / check` is already successful on the same exact SHA.
4. Download that SHA through the GitHub archive API into the hosted runner temporary workspace.
5. Extract the archive without copying Git history.
6. Revoke the source token immediately after source acquisition.
7. Run private project commands with no private source credential present.

BuildFarm must not use `actions/checkout` against the private project repository.

### Result token lifecycle

After the private task completes, create a new short-lived token with the minimum permission needed to write the Check Run. Post the sanitized result to the exact private commit, then revoke that result token.

Do not keep one installation token alive across source acquisition and result reporting.

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

Runner-local logs are sanitized before any failure detail is sent back to the private repository. At minimum, sanitization must remove source excerpts, absolute source-root paths, obvious credential/token forms, ANSI control sequences, and unbounded lines/output.

Sanitized diagnostics are written to the private commit as a GitHub Check Run.

## Build/check separation

The platform-independent `check` task is run once per exact SHA.

Platform build and delivery tasks require a successful private `BuildFarm / check` Check Run on that same SHA; they must not repeat analyze/test merely because a Windows or Android build is requested.

Use `concurrency` + `cancel-in-progress` so a newer task supersedes an older task of the same project/task class.

Do not high-frequency retry CI. Read the private Check Run, make a concrete source/config change, move `ci/buildfarm` when appropriate, then run again.

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
