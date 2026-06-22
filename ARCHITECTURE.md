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
- Snapshot creation

---

## State Layer

The state layer contains deterministic application logic.

Examples include:

- Insights processing
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
       ▼

    ui_cache
       │
       ▼

    ui_view
       │
       ▼

Map
Open Ports
LAN/LOCAL Services
Unmapped Services
```

Session state exists only while the application is running.

### Historical Flow

Used for long-term analysis.

```text
model_snapshot
       │
       ▼

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

Historical state survives application restarts.

---

## State Stores

### model_snapshot

Represents the current network snapshot.

This state is transient and replaced during each polling cycle.

### ui_cache

Session-scoped state.

Contains activity accumulated during the current application session.

Used by:

- Interactive Map
- Open Ports
- LAN/LOCAL Services
- Unmapped Services

Cleared when the application exits or the user clears the cache.

### insights

Persistent historical state.

Maintains rolling activity history for:

- Applications
- Countries
- Providers (ASN)
- Ports

Loaded at startup and periodically written to disk.

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

---

## Repository Structure

```text
src/tapmap/
├── app.py          Controller and callback orchestration
├── config.py       Application configuration
├── runtime.py      Runtime initialization
│
├── model/          Network collection and GeoIP enrichment
├── state/          Application state and decision logic
├── ui/             Dash and Plotly rendering
├── geodb/          GeoIP database management
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
5. The local web application is started.

---

## Related Documentation

- [README](README.md)
- [CONTRIBUTING](CONTRIBUTING.md)
- [SECURITY](SECURITY.md)
- [Docker](docs/docker.md)
- [GeoIP Database Management](docs/geodb-management.md)
- [Environment Variables](docs/environment-variables.md)
- [Backend Testing](docs/backend-testing.md)
