"""Turn live wattage into live grams of CO2.

Three steps, each degrading gracefully so the dashboard never blocks or crashes
on a flaky network:

1. Geolocate the machine from its public IP (ip-api.com, keyless).
2. Look up the grid's carbon intensity (gCO2eq per kWh) for that location.
3. The render loop multiplies the live package power by that intensity.

Carbon-intensity sources, tried in order:
- Electricity Maps, if WATTCHER_EMAPS_TOKEN is set — live, global, best quality.
- The UK National Grid API (carbonintensity.org.uk), keyless, if we're in GB.
- A static table of recent annual averages otherwise — not live, but the right
  order of magnitude, and it makes the feature work anywhere with no key.

Power (W) -> emissions: gCO2/h = (watts / 1000) * intensity, since
intensity is per kWh and watts/1000 is kW. Cumulative grams come from the
package joules: kWh = joules / 3.6e6, then * intensity.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

GEO_URL = "http://ip-api.com/json/?fields=status,country,countryCode,regionName,lat,lon"
EMAPS_URL = "https://api.electricitymap.org/v3/carbon-intensity/latest"
UK_URL = "https://api.carbonintensity.org.uk/intensity"
TIMEOUT = 4.0

# Recent (~2023) annual-average grid carbon intensity, gCO2eq/kWh. Coarse, but
# enough to be useful as a keyless fallback. Source: Ember / Our World in Data.
ANNUAL_AVERAGE = {
    "FR": 56, "SE": 41, "NO": 30, "CH": 45, "CA": 120, "BR": 100, "FI": 79,
    "GB": 190, "ES": 170, "IT": 270, "US": 370, "DE": 380, "JP": 470,
    "CN": 530, "AU": 510, "IN": 630, "PL": 660, "ZA": 710,
}
WORLD_AVERAGE = 480

JOULES_PER_KWH = 3.6e6


@dataclass
class Location:
    country_code: str
    label: str
    lat: float
    lon: float


@dataclass
class CarbonIntensity:
    grams_per_kwh: float
    zone: str  # human-readable location/grid zone
    source: str  # where the number came from
    live: bool  # True for real-time APIs, False for the annual-average fallback

    def grams_per_hour(self, watts: float) -> float:
        return (watts / 1000.0) * self.grams_per_kwh

    def grams_for_joules(self, joules: float) -> float:
        return (joules / JOULES_PER_KWH) * self.grams_per_kwh


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict | None:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None  # offline, rate-limited, blocked — caller falls back


def geolocate() -> Location | None:
    data = _get_json(GEO_URL)
    if not data or data.get("status") != "success":
        return None
    region = data.get("regionName") or ""
    country = data.get("country") or data.get("countryCode") or "?"
    label = f"{region}, {country}" if region else country
    return Location(
        country_code=data.get("countryCode") or "",
        label=label,
        lat=float(data.get("lat", 0.0)),
        lon=float(data.get("lon", 0.0)),
    )


def _from_electricitymaps(loc: Location, token: str) -> CarbonIntensity | None:
    url = f"{EMAPS_URL}?lat={loc.lat}&lon={loc.lon}"
    data = _get_json(url, headers={"auth-token": token})
    if not data or "carbonIntensity" not in data:
        return None
    return CarbonIntensity(
        grams_per_kwh=float(data["carbonIntensity"]),
        zone=str(data.get("zone") or loc.label),
        source="Electricity Maps (live)",
        live=True,
    )


def _from_uk(loc: Location) -> CarbonIntensity | None:
    data = _get_json(UK_URL)
    try:
        intensity = data["data"][0]["intensity"]  # type: ignore[index]
        grams = intensity.get("actual") or intensity.get("forecast")
    except (TypeError, KeyError, IndexError):
        return None
    if grams is None:
        return None
    return CarbonIntensity(
        grams_per_kwh=float(grams),
        zone=loc.label,
        source="UK National Grid (live)",
        live=True,
    )


def _from_table(loc: Location | None) -> CarbonIntensity:
    code = loc.country_code if loc else ""
    grams = ANNUAL_AVERAGE.get(code, WORLD_AVERAGE)
    zone = loc.label if loc else "unknown location"
    where = code if code in ANNUAL_AVERAGE else "world"
    return CarbonIntensity(
        grams_per_kwh=grams,
        zone=zone,
        source=f"annual average ({where})",
        live=False,
    )


def fetch_carbon() -> CarbonIntensity:
    """Best available carbon intensity for this machine. Always returns a value
    (falls back to a static average); blocking, so call it off the UI thread."""
    loc = geolocate()
    token = os.environ.get("WATTCHER_EMAPS_TOKEN")
    if loc and token:
        result = _from_electricitymaps(loc, token)
        if result:
            return result
    if loc and loc.country_code == "GB":
        result = _from_uk(loc)
        if result:
            return result
    return _from_table(loc)
