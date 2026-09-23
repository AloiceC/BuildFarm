# MintLink on BuildFarm

Source repository: `AloiceC/MintLink` (private)

BuildFarm must not mirror MintLink source. The private repository remains the source of truth.

## Current toolchain target

The previous local self-hosted baseline exposed a real Android toolchain incompatibility: Android API 37.0 requires a newer Android Gradle Plugin than the Flutter 3.41.9-era project was using.

The hosted-runner migration therefore validates this baseline before reconnecting private source:

- Flutter stable: 3.47.5
- JDK: 17
- Android API: 37.0
- AGP: 9.1.1 minimum for API 37.0
- Gradle: 9.3.1 for AGP 9.1.1
- Android SDK Build Tools: 37.x available, with AGP 9.1.1 compatibility checked against official Android documentation
- Rust / FRB / Drift versions remain project-owned decisions and must be reconciled in the private repository before the private build workflow is considered stable.

See the private MintLink repository document `docs/CI_BUILD_LESSONS.md` for the detailed history and lessons from the abandoned local self-hosted bootstrap.

## Onboarding stages

1. Run BuildFarm's public `Flutter Android 37 smoke` workflow against a generated dummy Flutter app. No private token is involved.
2. If the smoke is green, update/reconcile the MintLink private repository toolchain to the proven baseline.
3. Add `MINTLINK_SOURCE_TOKEN` to BuildFarm as a fine-grained Actions secret scoped only to `AloiceC/MintLink` with `Contents: Read`.
4. Add a MintLink-specific manual workflow. It must hard-code `AloiceC/MintLink`, use `persist-credentials: false`, and must not expose verbose private compiler logs publicly.
5. Define a private delivery path before uploading APK/Windows binaries or detailed failure logs. Do not upload them as public BuildFarm artifacts.

## Mirror policy

Use trusted/verifiable mirrors where appropriate and keep an official fallback where practical. Current approved examples include CFUG Flutter/Pub mirrors and Aliyun's Gradle distribution mirror. Android SDK packages remain on Google's official source unless an equivalently trustworthy and verifiable mirror is identified.
