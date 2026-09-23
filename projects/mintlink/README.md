# MintLink on BuildFarm

Source repository: `AloiceC/MintLink` (private)

BuildFarm must not mirror MintLink source. The private repository remains the source of truth.

## BuildFarm v1 requirement

MintLink must use the same private-project contract as every other BuildFarm v1 integration:

- private handoff ref: `ci/buildfarm`;
- runtime resolution to an exact commit SHA;
- a dedicated MintLink GitHub App with only `Metadata: read + Contents: read + Checks: write`;
- GitHub archive API download of the exact SHA into the hosted runner temporary workspace;
- no `actions/checkout` against the private source repository and no Git history copy;
- immediate source-token revocation after source acquisition;
- private compiler stdout/stderr kept out of public BuildFarm logs;
- sanitized private failure diagnostics written back as Check Runs using a fresh short-lived token;
- normal private binaries discarded after verification;
- owner test packages encrypted with the owner's age public recipient before public artifact upload;
- no self-hosted runner delivery path.

The older fine-grained-PAT / private-delivery proposal is superseded by BuildFarm v1 and must not be implemented.

## Current toolchain target

The previous local bootstrap exposed a real Android toolchain incompatibility: Android API 37.0 requires a newer Android Gradle Plugin than the older Flutter-era project was using.

The public toolchain smoke currently validates this public-safe baseline:

- Flutter stable: 3.47.5
- JDK: 17
- Android API: 37.0
- AGP: 9.1.1 minimum for API 37.0
- Gradle: 9.3.1 for AGP 9.1.1

Rust / FRB / Drift versions and the final private build manifest remain project-owned decisions in the MintLink repository. See its private `docs/CI_BUILD_LESSONS.md` before changing the toolchain.

## Mirror policy

Use trusted/verifiable mirrors where appropriate and keep an official fallback where practical. Current approved examples include CFUG Flutter/Pub mirrors and a probed Aliyun Gradle distribution mirror. Android SDK packages remain on Google's official source unless an equivalently trustworthy and verifiable mirror is deliberately approved.
