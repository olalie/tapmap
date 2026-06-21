TAPMAP_README_VERSION=1

GeoIP databases used by TapMap.

Recommended: install databases from GeoIP Database Management in TapMap.

Manual installation is also supported.

If running in Docker, this folder is mapped from the host to /data in the container.

Supported providers:

MaxMind GeoLite2
- GeoLite2-City.mmdb
- GeoLite2-ASN.mmdb
- https://dev.maxmind.com/geoip/geolite2-free-geolocation-data

DB-IP Lite
- DBIP-City.mmdb
- DBIP-ASN.mmdb
- DB-IP files must be renamed to the filenames above.
- https://db-ip.com/db/lite.php
