"""Track 30-day novelty per dimension and evaluate connection significance."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .insights_state import InsightsState

REASON_NEW_APP = "new_app"
REASON_NEW_COUNTRY = "new_country"
REASON_NEW_PROVIDER = "new_provider"
REASON_NEW_PORT = "new_port"
REASON_VERIFICATION_FAILED = "verification_failed"

_DIM_APPLICATIONS = "applications"
_DIM_COUNTRIES = "countries"
_DIM_PROVIDERS = "providers"
_DIM_PORTS = "ports"
_DIM_VERIFICATION_FAILED = "verification_failed"

# Order matches the Significant Connection event schema.
_KEPT_CACHE_ITEM_FIELDS = (
    "proto",
    "ip",
    "port",
    "service",
    "lat",
    "lon",
    "process_name",
    "exe",
    "city",
    "country",
    "country_code",
    "asn",
    "asn_org",
    "app_name",
    "app_creator",
    "app_verification_status",
    "app_signature_state",
    "app_signature_state_details",
)


class SignificanceHistory:
    """Own 30-day novelty state for the four Insights dimensions and verification failures."""

    def __init__(
        self,
        last_seen: dict[str, dict[Any, int]],
        verification_failed: dict[str, int],
    ) -> None:
        self.last_seen = last_seen
        self.verification_failed = verification_failed

    @classmethod
    def from_insights_state(cls, insights_state: InsightsState) -> SignificanceHistory:
        """Derive runtime last_seen state from persisted Insights bitmasks.

        Read-only against insights_state.insights: does not age or mutate the
        Insights bitmasks. verification_failed is held by direct reference,
        not copied, since it has no separate persisted representation of its
        own outside InsightsState.
        """
        last_seen: dict[str, dict[Any, int]] = {
            _DIM_APPLICATIONS: {},
            _DIM_COUNTRIES: {},
            _DIM_PROVIDERS: {},
            _DIM_PORTS: {},
        }

        for dimension in (_DIM_APPLICATIONS, _DIM_COUNTRIES, _DIM_PROVIDERS):
            source = insights_state.insights.get(dimension)
            if not isinstance(source, dict):
                continue
            for key, entry in source.items():
                day = _last_seen_day(entry)
                if day is not None:
                    last_seen[dimension][key] = day

        ports_source = insights_state.insights.get(_DIM_PORTS)
        if isinstance(ports_source, dict):
            for key, entry in ports_source.items():
                day = _last_seen_day(entry)
                if day is None:
                    continue
                try:
                    last_seen[_DIM_PORTS][int(key)] = day
                except (TypeError, ValueError):
                    continue

        return cls(last_seen=last_seen, verification_failed=insights_state.verification_failed)

    def check_and_update(self, dimension: str, key: Any, today: int) -> bool:
        """Return True if key was not seen within the last 30 days for dimension.

        Always records key as seen today, regardless of the result.
        """
        target = (
            self.verification_failed
            if dimension == _DIM_VERIFICATION_FAILED
            else self.last_seen[dimension]
        )
        last_day = target.get(key)
        is_new = last_day is None or (today - last_day) >= 30
        target[key] = today
        return is_new


def _last_seen_day(entry: Any) -> int | None:
    """Return the most recent observation day encoded in a persisted {l, m} Insights entry."""
    if not isinstance(entry, dict):
        return None
    anchor_day = entry.get("l")
    mask = entry.get("m")
    if not isinstance(anchor_day, int) or not isinstance(mask, int) or mask == 0:
        return None
    lowest_set_bit_position = (mask & -mask).bit_length() - 1
    return anchor_day - lowest_set_bit_position


def get_significant(
    item: dict[str, Any],
    history: SignificanceHistory,
    now: datetime,
) -> dict[str, Any] | None:
    """Evaluate one PUBLIC connection for significance.

    Checks all applicable criteria unconditionally, since check_and_update()
    must record every observed value regardless of whether it turns out to be
    new. Returns None if no criterion applies. Caller is responsible for
    only invoking this for PUBLIC-scope connections.
    """
    today = now.date().toordinal()
    reasons: list[str] = []

    app_name = item.get("app_name")
    has_app_name = isinstance(app_name, str) and bool(app_name)

    if has_app_name:
        if history.check_and_update(_DIM_APPLICATIONS, app_name, today):
            reasons.append(REASON_NEW_APP)

        if item.get("app_verification_status") == "failed" and history.check_and_update(
            _DIM_VERIFICATION_FAILED, app_name, today
        ):
            reasons.append(REASON_VERIFICATION_FAILED)

    country_code = item.get("country_code")
    if (
        isinstance(country_code, str)
        and country_code
        and history.check_and_update(_DIM_COUNTRIES, country_code, today)
    ):
        reasons.append(REASON_NEW_COUNTRY)

    asn_org = item.get("asn_org")
    if (
        isinstance(asn_org, str)
        and asn_org
        and history.check_and_update(_DIM_PROVIDERS, asn_org, today)
    ):
        reasons.append(REASON_NEW_PROVIDER)

    port = item.get("port")
    if isinstance(port, int) and history.check_and_update(_DIM_PORTS, port, today):
        reasons.append(REASON_NEW_PORT)

    if not reasons:
        return None

    event: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "reasons": reasons,
        "pid": item.get("pid"),
    }
    for field_name in _KEPT_CACHE_ITEM_FIELDS:
        event[field_name] = item.get(field_name)

    return event
