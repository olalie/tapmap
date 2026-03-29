# Repository Setup

## Git workflow

- main always stable
- all changes via branch and PR
- CI must be green before merge
- Windows artifact tested manually before merge
- squash merge only

## Release workflow

- version bump committed directly to main
- version defined in pyproject.toml
- tag (vX.X.X) triggers release workflow
- release workflow builds artifacts on Windows, Linux and macOS
- Docker image is built and pushed
- release is published after all artifacts and Docker image are ready

## Signing

- SSH signing enabled
- one signing key per machine (Windows, Linux, macOS)
- public keys registered in GitHub (user level)
- commits are signed automatically
- tags are signed automatically
- local verification via allowed_signers

## Branch protection

- main is protected
- PR required for normal changes
- CI checks required before merge
- direct push to main allowed for version bump (intentional exception)

## Immutable releases

- immutable releases enabled
- release assets cannot be modified after publish
- tags cannot be moved after publish
- release workflow uses:
  - create draft
  - upload assets
  - publish release

## CI expectations

- artifacts built on:
  - Windows
  - Linux
  - macOS
- Docker image tested in CI
- Docker supports:
  - linux/amd64
  - linux/arm64
- release workflow triggered only by tag

## Notes

- test commits for signing are done on a temporary branch and deleted after verification
- no test commits on main
- release artifacts include SHA256 checksums
