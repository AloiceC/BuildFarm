# Celeste Basecamp on BuildFarm

Source repository: `AloiceC/Celeste-Basecamp` (private)

This directory is intentionally a thin public adapter. The private repository remains the source of truth for source code, toolchain versions, lockfiles, build commands, compatibility history, and project status.

## Handoff

- fixed source repository: `AloiceC/Celeste-Basecamp`;
- fixed handoff ref: `ci/buildfarm`;
- runtime input is always resolved to an exact commit SHA before download;
- private build manifest: `.buildfarm/project.json` in the private repository.

The shared BuildFarm v1 workflow downloads the exact-SHA archive with the project's dedicated GitHub App, revokes the source token, suppresses private command output, and reports sanitized diagnostics back to the private commit.

## Runner

Celeste Basecamp currently uses the shared Windows private-project workflow on GitHub `windows-latest`, because the validation boundary includes a Windows Tauri executable build.

No self-hosted runner is part of the BuildFarm delivery path.

## Delivery

Normal validation uploads no private executable.

When acceptance delivery is explicitly requested, the project-owned manifest selects the test files, BuildFarm encrypts them with the configured age public recipient, and only the encrypted `.age` package is uploaded.
