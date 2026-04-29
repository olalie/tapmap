## Unreleased

### Insights
- Include all tied items in Top 5 lists based on 30-day activity

## 1.6.1 (2026-04-28)

### CI
- Fix Docker latest tag publishing in release workflow

### Docker
- Ensure latest tag always points to current release

### Notes
- No functional changes
- No changes to application behavior

## 1.6.0 (2026-04-28)

### Refactor
- Move codebase to src/tapmap
- Switch to python -m tapmap
- Align imports and test structure

### CI
- Update workflows to use CLI instead of file execution
- Add Docker smoke test to release workflow
- Ensure CI reflects real runtime usage

### Docker
- Install package with pip install .
- Use module entrypoint instead of direct script execution
- Align Docker and compose configuration

### Documentation
- Improve README introduction
- Refine insights section in README
- Fix formatting and spacing

### Maintenance
- Update GitHub Actions
- Skip CI for documentation-only changes


## 1.5.0 (2026-04-24)

### Features
- Add Insights panel with 30-day activity
  - Show new items today not seen in the last 30 days
  - Show most frequently observed items
  - Group by apps, providers, countries and ports
- Persist activity data across restarts

### Improvements
- Simplify status model to WAIT, OK and ERROR
- Standardize socket family values

### Testing
- Add unit tests for netinfo backends, model classification, geoinfo and public IP utilities

### Documentation
- Add repository setup and workflow documentation


## 1.4.3 (2026-03-29)

### Maintenance
- Change release workflow to draft, upload and publish flow


## 1.4.2 (2026-03-28)

### Fixes
- Publish Docker image for linux/amd64 and linux/arm64

### Documentation
- Clarify CLI usage
- Clarify Docker process visibility


## 1.4.1 (2026-03-26)

### Features
- Improve CLI help
- Document CLI usage
- Add Docker smoke test in build workflow

### Maintenance
- Add Docker Hub publish to release workflow
- Push Docker images with latest and version tags


## 1.4.0 (2026-03-25)

### Features
- Add macOS backend using lsof

### Fixes
- Run version check only for release tags

### Documentation
- Update backend testing documentation
- Update README and acknowledgements

### Maintenance
- Add macOS artifacts to release workflow


## 1.3.2 (2026-03-21)

### Fixes
- Show server host and Docker status in About view


## 1.3.1 (2026-03-20)

### Fixes
- Read version from pyproject


## 1.3.0 (2026-03-20)

### Features
- Add Linux Docker support

### Documentation
- Add Docker Hub usage instructions


## 1.2.0 (2026-03-17)

### Features
- Add Linux build and release artifacts

### Fixes
- Improve Linux ss handling before moving to psutil
- Make server port configurable via config and TAPMAP_PORT

### Improvements
- Use psutil backend for Linux and Windows

### Documentation
- Improve MkDocs configuration
- Update README

### Maintenance
- Update GitHub Actions workflows


## 1.1.0 (2026-03-10)

### Features
- Add pytest layout and CI test execution

### Improvements
- Refactor UI and backend structure

### Documentation
- Add MkDocs documentation
- Improve module docstrings


## 1.0.8 (2026-03-07)

### Fixes
- Show PID in terminal cache view

### Improvements
- Refactor UI, state handling and table helpers

### Documentation
- Add demo GIFs to README

### Maintenance
- Apply Ruff formatting
- Clean up project structure


## 1.0.7 (2026-02-28)

### Features
- Add LAN/LOCAL connections view
- Aggregate unmapped endpoints and add connection count
- Add checkbox to include or exclude system processes in open ports table

### Fixes
- Improve release packaging and CI workflows

### Improvements
- Refactor netinfo backend and status handling

### Documentation
- Update Help, About and README

### Maintenance
- Add CI workflows and release pipeline


## Earlier versions

Initial development and setup.
