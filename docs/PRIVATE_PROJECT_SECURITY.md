# Private project security model

BuildFarm is public. Any workflow that builds a private project must be designed under the assumption that **BuildFarm workflow files, run metadata, and normal Actions logs are public**.

## Non-negotiable rules

1. Never mirror or commit private project source into BuildFarm.
2. Never store private credentials in repository files. Use GitHub Actions secrets only.
3. Use one project-scoped credential per private project. Do not reuse a broad account-wide token across projects.
4. Private-source workflows must hard-code the allowed source repository. Do not accept an arbitrary `owner/repo` input while a private-source credential is available.
5. Prefer a fine-grained PAT or GitHub App token restricted to the exact private repository and the minimum permissions needed.
6. Source checkout credentials should be read-only (`Contents: Read`) whenever possible and must use `persist-credentials: false`.
7. Never run secret-bearing private-source jobs from `pull_request`, `pull_request_target`, or untrusted fork-controlled code. Initial private-project workflows are manual (`workflow_dispatch`) only.
8. Public BuildFarm artifacts are not suitable for private binaries, private logs, proprietary assets, or other private build output.
9. Commands that compile private source should not stream verbose compiler output into BuildFarm public logs by default. Detailed private logs need a private egress path before they are enabled.
10. Project-specific secrets must never be shared between project workflows unless the project owner explicitly broadens their scope.

## Recommended two-stage onboarding

### Stage A — public toolchain smoke

Before any private token is added, reproduce the required toolchain using a generated/public dummy project on the standard GitHub-hosted runner. This validates runner image, SDK, Gradle, Flutter/Rust/etc. compatibility without exposing the private source.

### Stage B — private source build

Only after Stage A is green:

- add a project-scoped read-only source token as a BuildFarm Actions secret;
- use a project-specific workflow with a fixed source repository;
- redirect verbose private compiler output away from the public console;
- define a private destination for failure logs and final binaries before uploading either;
- keep the public console limited to toolchain versions, high-level stages, exit status, hashes, and other non-sensitive metadata.

## Artifact policy

Do not use `actions/upload-artifact` for private-project binaries or detailed private logs in this public repository. Public BuildFarm artifacts must be treated as public.

For private projects, prefer a private destination owned by that project (for example, a private repository release or another explicitly approved private storage destination) using a separate narrowly-scoped write credential.

## Token naming convention

Project-specific secrets should make their scope obvious. Example for MintLink:

- `MINTLINK_SOURCE_TOKEN` — fine-grained token, only `AloiceC/MintLink`, `Contents: Read`.
- `MINTLINK_DELIVERY_TOKEN` — optional, only `AloiceC/MintLink`, minimum write permission required for the chosen private artifact destination.

Do not replace these with a single broad `repo` token unless there is no narrower supported option and the owner explicitly accepts that risk.
