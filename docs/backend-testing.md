# Backend testing (Windows, Linux, macOS, Docker)

This document summarizes testing of network backends used to collect socket data.

_Last reviewed: 2026-03-25 (Windows 11, Ubuntu 24.04.4 LTS, macOS on Apple M1; psutil, ss, lsof tested)_

## Scope

Tested combinations:

- Windows (native)
- Linux (native)
    - psutil vs ss
- macOS (native)
    - psutil vs lsof
- Docker
    - Linux host
        - psutil vs ss
    - macOS host
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

### Optional SYS_PTRACE testing

Tested:

- native Linux executable with setcap cap_sys_ptrace=ep
- Docker with --cap-add=SYS_PTRACE

Observed:

- no change in socket coverage
- no additional process metadata

Conclusion:
- SYS_PTRACE did not provide additional process information in this setup
- not required for the current backend

---

## macOS (native)

Tested combinations:

- psutil without root
- psutil with root
- lsof without root
- lsof with root

### psutil

Without root:

- psutil failed with AccessDenied
- no usable socket data

With root:

- full TCP and UDP socket data
- PID available for all sockets
- process metadata available

Conclusion:
- psutil requires root on macOS
- not suitable for normal GUI usage

### lsof

Without root:

- TCP socket data available
- reduced UDP coverage
- basic process metadata available

With root:

- increased socket coverage, mainly UDP
- process metadata unchanged

Conclusion:
- lsof provides usable data without root
- root improves socket coverage

### psutil vs lsof

- with root, similar socket coverage
- without root, only lsof is usable

Conclusion:
- lsof is the preferred backend for macOS

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

## Docker (macOS host)

Tested:

- Docker Desktop on macOS (Apple M1)
- alpine container with lsof

Observed:

- lsof returned only container-internal processes
- no access to macOS sockets or processes

Conclusion:
- Docker on macOS does not expose host network connections
- tools like lsof only see container-internal data
- not usable for this application

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
- macOS requires root for psutil, but lsof works without root
- socket coverage is consistent on Windows and Linux, but not on macOS where UDP coverage improves with root
- Docker on Linux can be used for network visualization only
- Docker on macOS and Windows cannot access host network data
- SYS_PTRACE did not improve process visibility in tested Linux setups

The application can rely on TCP and UDP data alone for map and service point visualization.

Process-level insights depend on platform and privileges, while network-level insights remain consistent in supported environments.
