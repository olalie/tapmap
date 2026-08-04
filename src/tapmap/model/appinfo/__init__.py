"""Application metadata for TapMap.

Modules in this package retrieve and combine metadata about
executables.

They contain no UI rendering or state transition logic.
"""

from .app_info import AppInfo, ApplicationMetadata, TrustVerdict

__all__ = ["AppInfo", "ApplicationMetadata", "TrustVerdict"]
