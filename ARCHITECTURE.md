# Architecture

## Overview

TapMap is a local-first network awareness application centered around an interactive world map.

The application periodically collects active network connections, enriches them with GeoIP information, and visualizes them as connection lines and map markers.

TapMap maintains two separate views of network activity:

- Session state used for real-time visualization and network inspection.
- Historical state used for insights and long-term analysis.

The map is the primary user experience. Additional functionality is exposed through panels and modal views rather than separate application pages.

---

## Design Principles

### Local-first

TapMap runs entirely on the local machine.

Network activity data is not sent to external services.

GeoIP lookups use local databases.

### Awareness, not control

TapMap is an awareness tool.

It visualizes and analyzes network activity but does not block, filter, or modify traffic.

### MVC-inspired architecture

TapMap follows an MVC-inspired architecture adapted for Dash and Plotly.

The architecture separates:

- Model: data collection and backend integration
- State: deterministic application logic
- UI: rendering and presentation
- Controller: callback orchestration and application flow

---

## High-Level Architecture

```text
                     app.py
                  (Controller)

                         │

         ┌───────────────┼───────────────┐
         │               │               │

         ▼               ▼               ▼

      model           state            ui
     (facade)       (logic)       (rendering)
```

---

## Model Layer

The model layer acts as a backend facade.

Platform-specific network collection, GeoIP enrichment, and snapshot construction are hidden behind a unified interface.

The rest of the application interacts with the model through:

```text
Model.snapshot()
```

rather than platform-specific implementations.

Examples:

```text
                 Model
                   │
                   ▼

                NetInfo
                   │

      ┌────────────┴────────────┐
      │                         │

      ▼                         ▼

PsutilNetInfo             LsofNetInfo
(Linux/Windows)            (macOS)
```

Responsibilities include:

- Socket inspection
- Process discovery
- Public IP discovery
- GeoIP enrichment
- Application information and platform verification
- Snapshot creation

---

## State Layer

The state layer contains deterministic application logic.

Examples include:

- Connection and Unmapped state (session-lifetime)
- Insights processing
- Significant Connections evaluation and history
- Menu state
- Modal state
- Keyboard handling
- Status calculations

The state layer contains no Dash rendering code.

---

## UI Layer

The UI layer builds Dash and Plotly output.

Responsibilities include:

- Map rendering
- Layout construction
- Modal content
- Daily Activity Report rendering
- Formatting helpers

The UI layer contains no business logic.

---

## GeoDB Subsystem

The GeoDB subsystem manages GeoIP database lifecycle and provider integrations.

The subsystem consists of:

- A UI integrated into the shared modal framework
- A service layer responsible for orchestration
- Provider-specific implementations for MaxMind and DB-IP

Responsibilities include:

- Database installation
- Database updates
- Validation
- Provider abstraction
- Status reporting

GeoDB is intentionally separated from the model layer.

The model layer consumes geolocation data, while GeoDB manages the databases and providers that make geolocation possible.

This separation isolates provider-specific concerns such as downloads, credentials, version checks, validation, and activation from network collection and snapshot generation.

---

## Lifecycle, Tray, and Autostart

TapMap runs as a single desktop process with two threads: the main thread owns the tray icon and application lifecycle, and the local web server runs on one background thread. The tray/lifecycle code communicates with the rest of the application only through a narrow interface and never reaches into `Model` or state stores directly.

All shutdown paths (tray Quit, the web UI Exit, process signals, and Docker container termination) go through the same coordinated shutdown sequence. Closing the browser tab does not stop TapMap; the browser and the TapMap process have independent lifetimes.

If a tray backend is unavailable, TapMap continues running without one; the web UI remains the way to interact with and exit the application.

Responsibilities:

- `lifecycle.py` — shutdown request handling, the tray run loop, and signal handlers.
- `tray.py` — tray icon and menu construction (Open TapMap / Quit TapMap).
- `autostart/` — per-platform login autostart integration.

### Autostart

TapMap can register itself to launch automatically at login. Each platform's native mechanism is the sole source of truth for current autostart state; it is never duplicated into `settings.json`.

- Windows: a per-user Scheduled Task, managed through Task Scheduler COM.
- macOS: `SMAppService.mainApp`.
- Linux: an XDG autostart desktop entry.

A one-time marker records that initial autostart setup has been handled. It never represents current ON/OFF state.

Docker/headless runs share the same lifecycle and shutdown model but have no tray and no autostart integration; container restart behavior is left to the container orchestration.

---

## Data Flow

Network activity enters the system through periodic snapshots.

```text
Network Connections
         │
         ▼

   Model.snapshot()
         │
         ▼

   model_snapshot
```

The snapshot drives two independent data flows.

### Session Flow

Used for real-time visualization.

```text
model_snapshot
       │
       ├──────────────────────┬───────────────────────┐
       │                      │                        │
       ▼                      ▼                        ▼

ConnectionAnalyzer         Open Ports        LAN/LOCAL Services
       │
  ┌────┴────┐
  │         │
  ▼         ▼

mapped   unmapped
  │         │
  ▼         ▼

ConnectionState   UnmappedState
  │                    │
  ▼                    ▼

ui_view            Unmapped Services
  │
  ▼

  Map
```

ConnectionAnalyzer classifies each PUBLIC connection as mapped (usable GeoIP) or unmapped, and routes it into ConnectionState or UnmappedState accordingly. ConnectionState and UnmappedState accumulate observations for the lifetime of the application session.

Open Ports and LAN/LOCAL Services are not accumulated. They are read directly from the current snapshot on each render and never pass through ConnectionAnalyzer or either session state store.

### AppInfo Flow

Application identity information is collected as part of normal snapshot processing. Expensive platform verification runs independently in the background.

```text
Model.snapshot()
       │
       ├── Application identity
       │
       ▼
   model_snapshot
       │
       ▼
ConnectionState / UnmappedState

Background verification
       │
       ▼
  AppInfo cache
       │
       ▼
 normal poll
       │
       ▼
ConnectionState / UnmappedState / SignificantConnections
```

Pending verification does not block snapshot creation or map updates. Completed verification information is merged into ConnectionState, UnmappedState, and SignificantConnections independently during subsequent polling.

### Historical Flow

Used for long-term analysis.

```text
model_snapshot
       │
       ▼

ConnectionAnalyzer
       │
       ├── per PUBLIC connection (mapped and unmapped):
       │      evaluate significance against SignificanceHistory
       │      │
       │      ▼
       │   significant? ──▶ SignificantConnections ──▶ significant_connections.json
       │
       ▼  (after the loop; mapped PUBLIC connections only)

process_insights()
       │
       ▼

   insights
       │
       ├── Insights Panel
       ├── Daily Activity Report
       └── Insights Log

       │
       ▼

  insights.json
```

Significant Connections evaluation runs per connection, inside the same loop that classifies mapped/unmapped connections, for every PUBLIC connection regardless of mapped/unmapped status. Novelty is judged against SignificanceHistory, an in-memory structure seeded from the persisted Insights bitmasks at startup and updated as each connection is evaluated; SignificanceHistory itself is not directly persisted. Connections judged significant are appended to SignificantConnections, a bounded, persisted event log.

Insights is a separate, batch-updated structure: after the per-connection loop completes, process_insights() updates the rolling 30-day Insights history using only the mapped PUBLIC connections observed in that poll. Unmapped PUBLIC connections are evaluated for significance but do not contribute to Insights.

Historical state survives application restarts.

---

## State Stores

### model_snapshot

Represents the current network snapshot.

This state is transient and replaced during each polling cycle.

### ConnectionState

Session-scoped state.

Accumulates mapped PUBLIC connections (usable GeoIP) observed during the current application session, routed here by ConnectionAnalyzer.

Retained entries may be enriched with completed AppInfo verification results during subsequent polling, even when the corresponding connection is no longer present in the latest snapshot.

Used by the Interactive Map.

Cleared when the application exits or the user clears the cache.

### UnmappedState

Session-scoped state.

Accumulates PUBLIC connections without usable GeoIP observed during the current application session, routed here by ConnectionAnalyzer.

Retained entries may be enriched with completed AppInfo verification results during subsequent polling, the same as ConnectionState.

Used by Unmapped Services.

Cleared when the application exits or the user clears the cache.

### SignificanceHistory

Runtime-only novelty tracking. Not directly persisted.

Records the last-seen day for each observed application, country, provider, and port, plus verification-failure history. The last-seen dictionaries are seeded once from the persisted Insights bitmasks at startup; verification-failure history is shared with InsightsState. The history is then updated in memory as each PUBLIC connection is evaluated.

Used by ConnectionAnalyzer to decide whether a connection is significant.

### SignificantConnections

Persistent historical state.

A bounded, chronological event log (most recent 500) of PUBLIC connections judged significant against SignificanceHistory, covering both mapped and unmapped connections.

Completed AppInfo verification results may update retained events during subsequent polling.

Loaded at startup and periodically written to disk as significant_connections.json.

### insights

Persistent historical state.

Maintains rolling 30-day activity history for:

- Applications
- Countries
- Providers (ASN)
- Ports

Populated only from mapped PUBLIC connections; unmapped PUBLIC connections do not contribute.

Loaded at startup and periodically written to disk as insights.json.

Used by:

- Insights Panel
- Daily Activity Report
- Insights Log

---

## Architectural Boundaries

The following boundaries should be preserved:

- model does not contain UI rendering
- state does not contain Dash or Plotly rendering
- ui does not contain business logic
- GeoIP database management remains isolated in geodb
- historical state remains separate from session state
- tray/lifecycle code does not directly access or manipulate model/state-owned application state

---

## Repository Structure

```text
src/tapmap/
├── app.py          Controller and callback orchestration
├── config.py       Application configuration
├── runtime.py      Runtime initialization
├── lifecycle.py    Shutdown coordination and the tray run loop
├── tray.py         System tray icon and menu
│
├── model/          Network collection and GeoIP enrichment
├── state/          Application state and decision logic
├── ui/             Dash and Plotly rendering
├── geodb/          GeoIP database management
├── autostart/      Per-platform login autostart integration
│
└── assets/         Static Dash assets
```

---

## Startup Flow

Application startup begins in:

```text
tapmap.__main__
    ↓
main()
    ↓
build_runtime()
    ↓
TapMap()
    ↓
run()
```

During startup:

1. Runtime configuration is created.
2. GeoIP services are initialized.
3. Historical insights are loaded from disk.
4. Dash callbacks are registered.
5. The tray and browser launch are initialized, the web server starts on a background thread, and the main thread runs the application lifecycle.

---

## Related Documentation

- [README](README.md)
- [CONTRIBUTING](CONTRIBUTING.md)
- [SECURITY](SECURITY.md)
- [Docker](docs/docker.md)
- [GeoIP Database Management](docs/geodb-management.md)
- [Environment Variables](docs/environment-variables.md)
- [Backend Testing](docs/backend-testing.md)
- [Application Information](docs/application-information.md)
- [AppInfo Performance](docs/appinfo-performance.md)
