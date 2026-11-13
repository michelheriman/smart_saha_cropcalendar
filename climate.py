"""
Climate data access and daily climatology.

Sources
-------
nasa_power  NASA POWER daily point API (no key, ~0.5 deg, 1981-present)
open_meteo  Open-Meteo archive API (ERA5-based reanalysis, no key for light use)
synthetic   Offline demo generator (for tests only; NOT real climate)

References
----------
Stackhouse et al., NASA POWER agroclimatology documentation.
Hersbach et al. (2020) ERA5, Q. J. R. Meteorol. Soc. 146, 1999-2049.
Allen et al. (1998) FAO-56 (solar geometry, Ra, day length).
Hargreaves & Samani (1985) Appl. Eng. Agric. 1(2), 96-99 (ET0).
"""
import os
import datetime as dt
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import requests

CACHE_DIR = os.environ.get("CROPCAL_CACHE", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache"))
DIM = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
CUM = np.concatenate([[0], np.cumsum(DIM)])
LAPSE = 0.0065  # K per m


class ClimateError(RuntimeError):
    pass


# ----------------------------------------------------------------------------------
# Fetchers (all return: DataFrame[tmax,tmin,prcp] indexed by date, grid elevation)
# ----------------------------------------------------------------------------------
def fetch_nasa_power(lat, lon, y0, y1):
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = dict(parameters="T2M_MAX,T2M_MIN,PRECTOTCORR", community="AG",
                  latitude=lat, longitude=lon, start=f"{y0}0101", end=f"{y1}1231", format="JSON")
    try:
        r = requests.get(url, params=params, timeout=180)
        r.raise_for_status()
        js = r.json()
        par = js["properties"]["parameter"]
        df = pd.DataFrame({"tmax": par["T2M_MAX"], "tmin": par["T2M_MIN"], "prcp": par["PRECTOTCORR"]})
    except Exception as e:  # network, HTTP, JSON structure
        raise ClimateError(f"NASA POWER request failed: {e}") from e
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999, np.nan).sort_index()
    coords = js.get("geometry", {}).get("coordinates", [])
    elev = float(coords[2]) if len(coords) > 2 and coords[2] is not None else None
    return df, elev


def fetch_open_meteo(lat, lon, y0, y1):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = dict(latitude=lat, longitude=lon, start_date=f"{y0}-01-01", end_date=f"{y1}-12-31",
                  daily="temperature_2m_max,temperature_2m_min,precipitation_sum", timezone="GMT")
    try:
        r = requests.get(url, params=params, timeout=180)
        r.raise_for_status()
        js = r.json()
        d = js["daily"]
        df = pd.DataFrame({"tmax": d["temperature_2m_max"], "tmin": d["temperature_2m_min"],
                           "prcp": d["precipitation_sum"]}, index=pd.to_datetime(d["time"]))
    except Exception as e:
        raise ClimateError(f"Open-Meteo request failed: {e}") from e
    elev = js.get("elevation")
    return df.sort_index(), (float(elev) if elev is not None else None)


def synthetic_climate(lat, lon, y0, y1):
    """Plausible fake climate for offline tests. Not real data."""
    rng = np.random.default_rng(int(abs(lat) * 1000 + abs(lon) * 10))
    days = pd.date_range(f"{y0}-01-01", f"{y1}-12-31")
    doy = days.dayofyear.values
    hot_day = 200 if lat >= 0 else 17
    ang = 2 * np.pi * (doy - hot_day) / 365.25
    base = 28 - 0.33 * abs(lat)
    amp = 0.22 * abs(lat) + 1.0
    tm = base + amp * np.cos(ang) + rng.normal(0, 2.2, len(days))
    dtr = 9 + 3 * np.sin(ang)
    tmax, tmin = tm + dtr / 2, tm - dtr / 2
    wet = np.clip(np.cos(ang), 0, None)  # wet season in local summer
    if abs(lat) < 28:       # tropical/subtropical summer-rainfall regime
        p_wet = 0.12 + 0.55 * wet
    elif abs(lat) < 45:     # mediterranean-like winter rain
        p_wet = 0.12 + 0.35 * np.clip(-np.cos(ang), 0, None)
    else:                   # even distribution
        p_wet = np.full(len(days), 0.35)
    rain = np.where(rng.random(len(days)) < p_wet, rng.exponential(9, len(days)), 0.0)
    return pd.DataFrame({"tmax": tmax, "tmin": tmin, "prcp": rain}, index=days), 0.0


FETCHERS = {"nasa_power": fetch_nasa_power, "open_meteo": fetch_open_meteo, "synthetic": synthetic_climate}


def get_daily(lat, lon, source="nasa_power", y0=None, y1=None, use_cache=True):
    if source not in FETCHERS:
        raise ClimateError(f"Unknown source '{source}'. Valid: {', '.join(FETCHERS)}")
    y1 = y1 or dt.date.today().year - 1
    y0 = y0 or y1 - 29
    if y0 > y1:
        raise ClimateError("start_year must be <= end_year")
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{source}_{lat:.2f}_{lon:.2f}_{y0}_{y1}.csv.gz")
    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        elev = df.attrs.get("elev")
        with open(path + ".elev") as fh:
            txt = fh.read().strip()
        elev = None if txt == "None" else float(txt)
        return df, elev, dict(source=source, y0=y0, y1=y1, cached=True)
    df, elev = FETCHERS[source](lat, lon, y0, y1)
    if use_cache and source != "synthetic":
        df.to_csv(path)
        with open(path + ".elev", "w") as fh:
            fh.write(str(elev))
    return df, elev, dict(source=source, y0=y0, y1=y1, cached=False)


# ----------------------------------------------------------------------------------
# Solar geometry, ET0 (FAO-56)
# ----------------------------------------------------------------------------------
def solar_geometry(lat):
    """Return (Ra in mm/day equivalent, day length in hours) for 365 days (FAO-56 eq. 21-34)."""
    J = np.arange(1, 366)
    phi = np.radians(np.clip(lat, -89.5, 89.5))
    dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365)
    dec = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return ra * 0.408, 24 / np.pi * ws


def et0_hargreaves(tmax, tmin, ra_mm):
    tmean = (tmax + tmin) / 2
    return np.maximum(0.0023 * (tmean + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0.1)) * ra_mm, 0)


# ----------------------------------------------------------------------------------
# Climatology
# ----------------------------------------------------------------------------------
@dataclass
class Climatology:
    lat: float
    lon: float
    tmax: np.ndarray        # mean daily max (365)
    tmin: np.ndarray        # mean daily min
    tmean: np.ndarray
    tmax_hi: np.ndarray     # 90th percentile of daily max (heat-risk proxy)
    tmin_lo: np.ndarray     # 10th percentile of daily min (frost-risk proxy)
    p: np.ndarray           # mean daily precipitation, mm
    et0: np.ndarray         # Hargreaves-Samani ET0, mm/day
    daylen: np.ndarray      # hours
    n_years: int
    meta: dict

    def monthly(self):
        out = []
        for m in range(12):
            s = slice(CUM[m], CUM[m + 1])
            out.append(dict(tmean=float(self.tmean[s].mean()), tmax=float(self.tmax[s].mean()),
                            tmin=float(self.tmin[s].mean()), precip_mm=float(self.p[s].sum()),
                            et0_mm=float(self.et0[s].sum())))
        return out


def _matrix(d, col):
    years = d.index.year.values
    ys = np.unique(years)
    mat = np.full((len(ys), 365), np.nan)
    doy0 = CUM[d.index.month.values - 1] + d.index.day.values - 1
    mat[np.searchsorted(ys, years), doy0] = d[col].values
    return mat


def _pool(mat, half):
    return np.concatenate([np.roll(mat, k, axis=1) for k in range(-half, half + 1)], axis=0)


def build_climatology(df, lat, lon, grid_elev=None, site_elev=None, meta=None):
    d = df[~((df.index.month == 2) & (df.index.day == 29))].copy()
    d = d.dropna(subset=["tmax", "tmin"])
    meta = dict(meta or {})
    # optional lapse-rate correction when user elevation differs from grid elevation
    corr = 0.0
    if site_elev is not None and grid_elev is not None:
        corr = -LAPSE * (site_elev - grid_elev)
        d["tmax"] += corr
        d["tmin"] += corr
    meta.update(grid_elevation_m=grid_elev, site_elevation_m=site_elev, lapse_correction_c=round(corr, 2))
    d["prcp"] = d["prcp"].clip(lower=0)
    tx, tn, pr = _matrix(d, "tmax"), _matrix(d, "tmin"), _matrix(d, "prcp")
    if tx.shape[0] < 5:
        raise ClimateError("Fewer than 5 years of usable data; cannot build a climatology.")
    tx_pool, tn_pool, pr_pool = _pool(tx, 3), _pool(tn, 3), _pool(pr, 7)
    tmax = np.nanmean(tx_pool, axis=0)
    tmin = np.nanmean(tn_pool, axis=0)
    p = np.nanmean(pr_pool, axis=0)
    tmax_hi = np.nanpercentile(_pool(tx, 7), 90, axis=0)
    tmin_lo = np.nanpercentile(_pool(tn, 7), 10, axis=0)
    ra, daylen = solar_geometry(lat)
    et0 = et0_hargreaves(tmax, tmin, ra)
    meta["n_years"] = int(tx.shape[0])
    return Climatology(lat, lon, tmax, tmin, (tmax + tmin) / 2, tmax_hi, tmin_lo, p, et0, daylen,
                       int(tx.shape[0]), meta)


def get_climatology(lat, lon, source="nasa_power", y0=None, y1=None, site_elev: Optional[float] = None,
                    use_cache=True):
    df, grid_elev, meta = get_daily(lat, lon, source, y0, y1, use_cache)
    return build_climatology(df, lat, lon, grid_elev, site_elev, meta)
