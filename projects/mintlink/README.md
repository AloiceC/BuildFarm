# MintLink on BuildFarm

Source repository: `AloiceC/MintLink` (private)

BuildFarm must not mirror MintLink source. The private repository remains the source of truth for source code, lockfiles, toolchain versions, build manifests, architecture, compatibility history, and project status.

## Current public toolchain research

The existing `Flutter Android 37 smoke` workflow is a public generated-project smoke test only. It does not acquire MintLink private source and therefore sits outside the private-source handoff path.

Its current public compatibility baseline is:

- Flutter stable: 3.47.5;
- JDK: 17;
- Android API: 37.0;
- AGP: 9.1.1;
- Gradle: 9.3.1.

MintLink-specific compatibility history remains in the private repository's `docs/CI_BUILD_LESSONS.md`.

## BuildFarm v1 private onboarding

MintLink private-source onboarding must use the shared BuildFarm v1 contract documented in `docs/PRIVATE_PROJECT_SECURITY.md`:

- private handoff ref `ci/buildfarm`;
- exact commit SHA locking;
- one MintLink-only GitHub App with Metadata read + Contents read + Checks write;
- GitHub archive API instead of private `actions/checkout`;
- immediate source-token revocation;
- suppressed public compiler/test output;
- sanitized Check Run diagnostics written to the private commit with a fresh report token;
- no raw APK/EXE/ZIP public artifacts;
- age-encrypted acceptance delivery only when explicitly requested;
- standard GitHub-hosted runner, not self-hosted delivery.

The private-project toolchain and build commands must come from MintLink's own private BuildFarm manifest rather than being duplicated into this public adapter.
