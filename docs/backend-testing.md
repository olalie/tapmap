# Backend testing (Windows, Linux and Docker)

This document summarizes testing of network backends used to collect socket data.

_Last reviewed: 2026-03-18 (Ubuntu 24.04.4 LTS, kernel 6.17.0-19-generic, psutil 7.2.2, ss from iproute2 6.1.0)_

## Scope

Tested combinations:

- Windows (native)
- Linux (native)
    - psutil vs ss
- Docker
    - Linux host
        - psutil vs ss
    - Windows host

The goal was to verify:

- completeness of TCP and UDP socket data
- availability of process metadata (PID, process name, executable, command line)

---

## Windows (native)

- psutil returned full TCP and UDP socket data
- process metadata was available for most sockets
- no elevated privileges required for socket data

### With vs without administrator privileges

- Running as administrator provided slightly more process metadata
- Most process information was already available without elevation

Conclusion:
- Windows provides strong support for both network data and process mapping
- elevation has limited impact

---

## Linux (native)

### Without root

- psutil and ss returned the same number of sockets
- TCP and UDP coverage was identical
- process information was only available for sockets owned by the current user

Conclusion:
- socket data is reliable without root
- process metadata is limited

### With root

- psutil and ss returned the same sockets as without root
- full process metadata was available for almost all sockets

Conclusion:
- root improves process visibility significantly
- socket coverage is unchanged

### With vs without root

- Without root, process metadata was limited to a subset of sockets
- With root, process metadata was available for almost all sockets

Conclusion:
- root has a significant impact on process visibility on Linux

### psutil vs ss

- no meaningful difference in socket coverage
- differences were limited to:
  - status naming (UNCONN vs NONE)
  - formatting of process names and command lines
- both backends identified the same sockets

Conclusion:
- psutil is sufficient as the Linux backend
- ss does not provide a practical advantage in native Linux

---

## Docker (Linux host)

- TCP and UDP socket data was available
- process metadata (PID, process name, executable, command line) was not available

Conclusion:
- Docker provides usable network data
- process-to-socket mapping is not available
- suitable for network visualization, not for process inspection

### psutil vs ss (Docker, Linux)

- no meaningful difference was observed
- both backends returned the same practical TCP and UDP socket coverage
- both backends were equally limited by container isolation
- neither backend provided usable process metadata

Conclusion:
- psutil is sufficient in Docker on Linux
- ss does not provide a practical advantage in this environment

---

## Docker (Windows host)

- socket data and process mapping were not reliable
- results were inconsistent and incomplete

Conclusion:
- Docker on Windows is not supported for this application

---

## Overall conclusion

- psutil is sufficient across supported environments
- Windows provides strong process visibility without elevation
- Linux requires root for full process metadata
- socket coverage is consistent regardless of privileges
- Docker on Linux can be used for network visualization only
- Docker on Windows is not supported

The application can rely on TCP and UDP data alone for map and service point visualization.

Process-level insights depend on platform and privileges, while network-level insights remain consistent in supported environments.
