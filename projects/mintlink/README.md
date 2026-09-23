# MintLink on BuildFarm

Source repository: `AloiceC/MintLink` (private).

MintLink uses the shared BuildFarm v1 private-source lifecycle. BuildFarm never mirrors MintLink source or Git history. The private repository remains authoritative for source, dependencies, Android overlays, Rust/FRB settings, project status, and build lessons.

## Handoff

Normal input is the private ref `ci/buildfarm`. BuildFarm resolves it to an exact commit SHA, downloads that SHA through the GitHub archive API, and revokes the source token before any private build command runs.

The manual entry workflow is `.github/workflows/mintlink.yml`.

## GitHub App

Expected BuildFarm configuration:

- repository variable `MINTLINK_CLIENT_ID`
- repository secret `MINTLINK_PRIVATE_KEY`

The dedicated GitHub App is installed only on `AloiceC/MintLink` and requires:

- Metadata: read
- Contents: read
- Checks: write

No Contents write, Actions write, or Administration permission is required.

## Execution layer

MintLink uses `private-flutter-rust-v1.yml`, a thin execution layer over the common BuildFarm v1 security scripts.

It adds only the project class capabilities that ordinary Flutter v1 does not need:

- pinned Rust toolchain with rustfmt/clippy/test;
- Flutter Rust Bridge code generation before Dart `build_runner`;
- project-owned Android overlays;
- explicit Android 37.0 SDK/NDK package installation for Android tasks;
- project-owned AGP/Gradle pins used to patch generated Flutter scaffolding;
- Windows and Android build/delivery tasks.

The private `ci/buildfarm.toml` is the source of truth for these versions and paths.

## Tasks

- `check`: Rust validation → Flutter scaffolding → `pub get` → FRB codegen → Dart build_runner → analyze → tests.
- `build-android`: requires green `BuildFarm / check` for the same SHA; builds an Android Release APK, records safe size/hash metadata, then discards the raw APK.
- `build-windows`: same gate; builds Windows Release, records safe size/hash metadata, then discards the raw package.
- `deliver-android` / `deliver-windows`: same build path, but only the age-encrypted ciphertext is uploaded.

`age_recipient` remains blank until the owner configures the public recipient. The corresponding private key stays local.

## Android 37

MintLink intentionally tests Android 17 local-network permission behavior.

The project manifest currently targets Flutter 3.47.5, JDK 17, Android `platforms;android-37.0`, Build Tools 37.0.0, NDK 28.2.13676358, AGP 9.1.1, and Gradle 9.3.1. These values are copied here only as onboarding context; the private manifest is authoritative.
