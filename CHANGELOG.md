## Unreleased

### Features
- Add opt-in cross-namespace capture (`TAPMAP_CAPTURE_ALL_NETNS=1`, Linux + `pid: host`): aggregate connections from every other container's network namespace via `/proc/<pid>/net/*`, labeled by container (friendly names resolved through a mounted Docker socket, falling back to short ids). Default-off; degrades to host-only on error.

### Daily Activity Report
- Refine narrative wording and report tone
- Improve alignment between wording, recurrence visuals, and provider concentration curves
- Simplify provider concentration summaries

## 1.7.2 (2026-05-26)

### Features
- Add runtime location override using `TAPMAP_LON` and `TAPMAP_LAT`
- Skip external public-IP lookup when runtime coordinates are provided
- Add ENV local-location mode to status line and About view

### Testing
- Add focused regression tests for runtime location override parsing
- Add boundary and validation coverage for runtime coordinate parsing
- Add comprehensive regression coverage for rolling 30-day insights bitmaps
- Add boundary tests for bitmap aging, pruning, and re-observation semantics
- Clarify internal `anchor_day` bitmap semantics without changing persistence format

### Documentation
- Document runtime location override environment variables
- Document privacy behavior for automatic public-IP detection
- Document Daily Activity Report keyboard shortcut in README
- Update Help and About semantics for ENV location mode

### CI
- Clarify macOS build naming in artifact workflow

### Maintenance
- Ignore full Docker runtime directory
- Fix MkDocs README list rendering
- Remove unused Flask dependency

## 1.7.1 (2026-05-20)

### Improvements
- Integrate Insights Log into modal flow
  - Replace external log opening with internal modal drilldown
  - Remove Flask `/open-log` route
  - Remove OS-level log opening
  - Preserve on-demand log generation
  - Add navigation:
    Daily Activity Report -> Insights Log -> back to report

### UI
- Improve Insights Log layout and spacing
- Center terminal-style log block
- Preserve left-aligned fixed-width console formatting

## 1.7.0 (2026-05-20)

### Features
- Add Daily Activity Report
  - Summarize recent network activity
  - Show recurring activity patterns
  - Show provider concentration analysis
  - Show country activity visualization
  - Add generated activity log view
- Add generated insights log
  - Include detailed timelines for applications, providers, countries and ports
  - Add "Open generated log" support
- Add accordion-style grouped menu
  - Group actions and views into expandable sections
  - Add keyboard shortcut for Daily Activity Report
- Add globe logo to application header

### Improvements
- Improve insights persistence robustness
  - Save `insights.json` atomically
  - Recover safely from corrupt or invalid insights data
  - Prevent concurrent writers with single-instance PID lock handling
  - Handle stale lock files safely

### Refactor
- Extract insights persistence orchestration from `app.py`
- Remove dead established-state filtering logic
- Remove dead CSS rules

### Testing
- Add persistence regression tests
- Add tests for insights save/load handling and lock handling
- Expand Daily Activity Report and insights log test coverage

### Documentation
- Update README and Help for Daily Activity Report and historical insights

## 1.6.3 (2026-05-04)

### Improvements
- Add macOS x86_64 build (Intel)
- Improve artifact naming and consistency

### Notes
- No breaking changes
- No changes to application functionality
- Distribution and packaging improvements only

## 1.6.2 (2026-04-29)

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
