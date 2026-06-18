"""GeoDB services and provider integrations for TapMap.

Modules in this package manage GeoIP databases and
provider-specific operations.

They contain no UI rendering or Dash callbacks.
"""

from .service import GeoDbService

__all__ = ["GeoDbService"]
