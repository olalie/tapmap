# AppInfo startup performance

This document describes the investigation and resolution of a startup performance regression observed after AppInfo was introduced.

It records the observed problem, performance measurements, identified causes, alternative solutions considered, the chosen approach, its implementation, and the resulting startup performance.

_Last reviewed: 2026-08-16_

---

## Problem and goal

After AppInfo was introduced, TapMap showed a significant startup regression. Network connections and map lines that previously became visible almost immediately could take close to 10 seconds, or two to three network snapshot intervals, to appear.

The goal is to identify the cause of this regression and restore fast startup without removing AppInfo functionality or compromising the quality of the application information it provides.

---

## Investigation

Startup and AppInfo processing were measured to identify where the additional processing time was spent.

AppInfo was measured separately on Windows, macOS, and Linux. The measurements below identify the dominant operations and show the effect of the existing in-memory cache.

No verification behavior was changed during these measurements.

### Windows

The dominant operation was:

`Microsoft.Security.Extensions.FileSignatureInfo.GetFromFileStream()`

Measured:

- 102 active connection records
- 16 unique executables
- Cold AppInfo enrichment: ~5.43 s
- `GetFromFileStream()`: ~5.28 s, about 99% of measured AppInfo time
- Warm cached enrichment: effectively instantaneous

The cost increased significantly with executable size. VERSIONINFO lookup, publisher extraction, and the `WinVerifyTrust` fallback were comparatively inexpensive.

Conclusion:

- Windows startup cost is dominated by `FileSignatureInfo.GetFromFileStream()`
- large executables are particularly expensive to verify
- the existing AppInfo cache is effective after the initial lookup

### macOS

The dominant operation was:

`spctl -a -vvv --type execute <path>`

Measured:

- `spctl` took roughly 2.3 s per applicable application
- `codesign` inspection and verification were comparatively inexpensive
- cached repeat lookups were effectively instantaneous

The `spctl` check is used to obtain notarization information. Notarization is additional signature information and does not determine TapMap's verification status.

Conclusion:

- macOS startup cost is dominated by `spctl`
- the expensive operation provides notarization information rather than the primary verification result
- the existing AppInfo cache is effective after the initial lookup

### Linux

The dominant operation was:

`dpkg -V <package>`

Measured on Ubuntu:

- 44 connection records
- 3 unique executables
- Cold AppInfo enrichment: ~4.4–6.7 s
- `dpkg -V`: ~3.4–5.0 s, about 75–77% of cold AppInfo time
- Warm cached enrichment: effectively instantaneous

Secondary costs were:

- `dpkg -S <path>` for package ownership lookup
- `apt-cache policy <package>` for repository/origin lookup

`dpkg -V` verifies package integrity by checking files belonging to the package. Its cost can therefore increase with package size and file count.

Conclusion:

- Linux startup cost is dominated by `dpkg -V`
- package ownership and repository lookups add smaller secondary costs
- the existing AppInfo cache is effective after the initial lookup

### Summary of measurement findings

The measurements confirm that AppInfo processing accounts for the observed startup delay, with most of the time spent in a small number of operating-system-specific operations.

On all three platforms, cold AppInfo processing is dominated by specific operating-system verification operations:

- Windows: `FileSignatureInfo.GetFromFileStream()`
- macOS: `spctl`
- Linux: `dpkg -V`

The existing in-memory cache is highly effective, making repeated AppInfo lookups effectively free.

The performance problem is therefore primarily a cold-start problem caused by expensive operating-system-specific verification work.

---

## Approaches considered

Several approaches were considered for reducing the cold-start impact while preserving the existing AppInfo functionality and verification semantics.

### Keep the current behavior

Rejected. The startup delay significantly degrades the user experience. Existing users are accustomed to seeing network connections and map lines almost immediately, while new users may experience a long delay before TapMap shows its main functionality.

Leaving the behavior unchanged could make TapMap feel slow or unresponsive and reduce the value of the immediate visual feedback that is an important part of the application.

### Loading message or splash screen

Rejected as the primary solution. A loading message would explain the delay, and a splash screen could hide it, but neither would restore fast access to network data and the map.

### Pure lazy loading

Not preferred as the primary solution. Deferring AppInfo until the user requests it would improve startup time, but could move the full verification delay to the first AppInfo interaction.

### Progressive background verification

Application identity information that can be obtained quickly is collected immediately, while information that depends on the expensive platform verification operations is collected in the background and becomes available progressively.

This preserves useful AppInfo at startup while moving the operations responsible for most of the measured delay out of the startup path.

### Parallel verification

Potentially useful as a secondary optimization. Processing multiple applications concurrently could reduce total collection time, but would not by itself remove AppInfo verification from the startup-critical path and could increase CPU, disk, or subprocess load.

### Persistent AppInfo cache

Potentially useful later. Persisting AppInfo between TapMap runs could substantially reduce repeated cold-start work, but requires reliable invalidation when an executable, signature, or installed package changes.

### Remove or selectively skip expensive verification

Rejected. Skipping verification based on executable size, package size, or similar heuristics would make verification behavior inconsistent and could weaken the existing verification semantics.

---

## Chosen approach

TapMap uses progressive background verification.

Application names and other identity information that can be obtained without the expensive verification operation are collected synchronously. Verification and signature information is collected in the background.

`app_creator` can be resolved in either phase. When creator information is available from inexpensive platform metadata, it is returned immediately. When determining the creator depends on deferred signature inspection, it becomes available with the background verification result.

The fields populated by background verification are:

- `app_verification_status`
- `app_signature_state`
- `app_signature_state_details`
- `app_creator` when it was not resolved during the initial identity lookup

Background verification uses two worker threads. AppInfo tracks verification already in progress for each executable so that repeated lookups do not submit duplicate work.

Completed verification results are stored in the existing AppInfo cache. The normal polling flow reads resolved information from this cache and updates the retained UI cache. This also allows AppInfo to be completed for an application whose connection is no longer present in the latest network snapshot but is still retained in the UI cache.

While verification information is pending, the UI represents it with a white status bullet and `Retrieving...`. If creator information is also still pending, it is shown as `Retrieving...` rather than `Unknown creator`. Once background verification completes, the resolved values replace the pending presentation on a subsequent poll.

The verification operations and their interpretation are unchanged. The architectural change affects when the expensive work is performed and when its results become visible, not the verification semantics.

### Platform guidance

The chosen approach is consistent with platform guidance for keeping applications responsive while performing time-consuming work.

Microsoft recommends keeping startup focused on the work required to make the application interactive, performing long-running work independently, and populating the user interface as data becomes available.

Apple similarly recommends keeping non-UI work off the main thread, performing it in the background, and updating the user interface when the required data is ready.

References:

- [Microsoft: Best practices for your WinUI app's startup performance](https://learn.microsoft.com/en-us/windows/apps/develop/performance/app-startup-performance)
- [Apple: Improving app responsiveness](https://developer.apple.com/documentation/xcode/improving-app-responsiveness)
