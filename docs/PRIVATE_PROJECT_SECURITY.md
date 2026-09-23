# Private project security model — BuildFarm v1

BuildFarm is public. Any workflow that builds a private project must assume that BuildFarm workflow files, run metadata, normal Actions logs, and uploaded BuildFarm artifacts are publicly observable.

## v1 private-project contract

Every private project uses the same contract:

1. The private project exposes a dedicated `ci/buildfarm` handoff ref.
2. BuildFarm resolves that ref at runtime and locks the run to an exact 40-character commit SHA. An operator may instead provide an exact SHA explicitly.
3. Each private project uses a dedicated GitHub App installed only on that private repository.
4. The GitHub App permissions are limited to:
   - Metadata: read;
   - Contents: read;
   - Checks: write.
5. BuildFarm creates a short-lived installation token scoped to the exact source repository, downloads an exact-SHA archive through the GitHub archive API, and immediately revokes the source token.
6. BuildFarm does not use `actions/checkout` to fetch private source and never copies private Git history into the public repository.
7. Private source exists only in the GitHub-hosted runner's temporary environment.
8. Private project commands run with stdout/stderr redirected to runner-temporary files. Public logs contain only high-level stage names, locked SHA, PASS/FAIL, duration, and similarly non-sensitive summaries.
9. Sanitized detailed diagnostics are written back to the private commit as a Check Run. Reporting uses a newly generated short-lived GitHub App token, which is revoked after the Check Run is written.
10. Normal validation never uploads raw private APK/EXE/ZIP output as a BuildFarm artifact.
11. When the owner explicitly requests an acceptance package, the package is encrypted with the owner's age public recipient before `actions/upload-artifact`. The age private key never enters BuildFarm.
12. Project lockfiles, toolchain versions, build manifests, compatibility notes, and project status remain owned by the private project repository. BuildFarm keeps only shared infrastructure and a thin public adapter.

## BuildFarm environment contract

Each onboarded private project gets one GitHub Actions environment named:

`private-<project-id>`

The environment uses the same variable/secret names for every project:

- variable `SOURCE_APP_CLIENT_ID` — client ID of the project's dedicated GitHub App;
- secret `SOURCE_APP_PRIVATE_KEY` — private key of that dedicated GitHub App;
- variable `AGE_RECIPIENT` — owner's age public recipient, required only when encrypted delivery is requested.

The GitHub App must be installed only on the corresponding private repository. Do not reuse one broad app across unrelated private projects in v1.

## Public adapter contract

`projects/<project-id>/adapter.json` is deliberately thin. It may contain only public-safe routing metadata:

- schema version;
- public project id;
- fixed private repository identifier;
- `ci/buildfarm` handoff ref;
- path to the private project-owned BuildFarm manifest.

The adapter must not duplicate project toolchain versions, dependency lock state, private build history, architecture, credentials, private URLs, or proprietary assets.

## Source acquisition

The shared private-project workflow:

- may use `actions/checkout` only for the public BuildFarm repository itself;
- must not use `actions/checkout` against private source;
- must scope the source installation token to one repository and `contents: read`;
- resolves `ci/buildfarm` or validates an explicitly supplied exact SHA;
- requests GitHub's archive endpoint for that exact SHA;
- follows the archive redirect without forwarding the Authorization header to the redirected object-storage URL;
- extracts into `$RUNNER_TEMP`;
- revokes the source installation token before any private build command runs.

## Diagnostics

Compiler and test stdout/stderr are not public BuildFarm output.

A failed private stage may be reduced to a sanitized diagnostic by:

- removing ANSI control sequences;
- replacing runner/source absolute paths;
- redacting common token/Authorization patterns;
- dropping common source-code frame lines;
- bounding line and character counts.

That sanitized diagnostic may be sent only to a Check Run attached to the private source commit.

## Artifact policy

Raw private build output is never uploaded from BuildFarm.

Ordinary validation may create binaries to prove that linking/packaging succeeds, but those files remain ephemeral and are discarded with the hosted runner.

Acceptance delivery is opt-in. BuildFarm packages only the private manifest's declared delivery files, encrypts the package with the configured age recipient, and uploads only the `.age` ciphertext. BuildFarm v1 pins the official age release used by the shared helper and verifies its published SHA-256 before use.

## Trigger discipline

Private-project workflows are manual (`workflow_dispatch`) in v1.

Do not attach private GitHub App credentials to `pull_request`, `pull_request_target`, fork-controlled code, or automatic high-frequency triggers. Inspect failures, make a concrete change, then run again.
