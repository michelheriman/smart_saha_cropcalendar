"""
Crop calendar Flask app.

Run:   python app.py            (http://127.0.0.1:5000)
API:   GET /api/calendar?lat=-18.9&lon=47.5&source=nasa_power&irrigated=false
       GET /api/calendar.csv?...    same parameters, CSV output
       GET /api/crops               default parameter table
Query parameters
  lat, lon        required (decimal degrees)
  elevation       optional site elevation (m); lapse-rate correction vs grid elevation
  source          nasa_power (default) | open_meteo | synthetic (offline demo)
  start_year, end_year   climatology period (default: last 30 complete years)
  irrigated       true/false (default false = rainfed)
  crops           comma-separated subset (default all 37); aliases such as grapewine are accepted
  start_month     1-12, first month shown in the calendar (default 1)
  overrides       JSON, e.g. {"maize":{"gdd":1700},"onion":{"dl_min":11}}
"""
import csv
import io
import json
import os
from dataclasses import asdict

from flask import Flask, Response, jsonify, request, send_file

from climate import ClimateError, get_climatology
from crops import CROPS, CROP_NAMES, merged_crops
from engine import run_calendar

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


class BadRequest(ValueError):
    pass


def _float(name, lo, hi, required=True):
    raw = request.args.get(name)
    if raw in (None, ""):
        if required:
            raise BadRequest(f"Missing parameter '{name}'.")
        return None
    try:
        v = float(raw)
    except ValueError:
        raise BadRequest(f"'{name}' must be a number.")
    if not lo <= v <= hi:
        raise BadRequest(f"'{name}' must be between {lo} and {hi}.")
    return v


def _int(name, lo, hi, default=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except ValueError:
        raise BadRequest(f"'{name}' must be an integer.")
    if not lo <= v <= hi:
        raise BadRequest(f"'{name}' must be between {lo} and {hi}.")
    return v


def compute():
    lat = _float("lat", -90, 90)
    lon = _float("lon", -180, 180)
    elev = _float("elevation", -430, 6000, required=False)
    y0, y1 = _int("start_year", 1981, 2100), _int("end_year", 1981, 2100)
    source = request.args.get("source", "nasa_power")
    irrigated = request.args.get("irrigated", "false").lower() in ("1", "true", "yes", "on")
    start_month = _int("start_month", 1, 12, 1)
    names = [n.strip() for n in request.args.get("crops", "").split(",") if n.strip()] or None
    overrides = None
    if request.args.get("overrides"):
        try:
            overrides = json.loads(request.args["overrides"])
            if not isinstance(overrides, dict):
                raise ValueError
        except ValueError:
            raise BadRequest("'overrides' must be a JSON object, e.g. {\"maize\":{\"gdd\":1700}}")
    try:
        crops = merged_crops(names, overrides)
    except (ValueError, TypeError) as e:
        raise BadRequest(str(e))

    clim = get_climatology(lat, lon, source, y0, y1, elev)
    cal = run_calendar(clim, crops, irrigated, start_month)
    monthly = clim.monthly()
    r = (start_month - 1) % 12
    monthly = monthly[r:] + monthly[:r]
    return dict(
        input=dict(lat=lat, lon=lon, elevation=elev, source=source, irrigated=irrigated),
        climate=dict(meta=clim.meta, monthly=monthly,
                     annual=dict(tmean=round(float(clim.tmean.mean()), 1),
                                 precip_mm=round(float(clim.p.sum())),
                                 et0_mm=round(float(clim.et0.sum())),
                                 frost_risk_days=int((clim.tmin_lo < 0).sum()))),
        calendar=cal,
        disclaimer="Agro-climatic feasibility windows computed from a daily climatology; they are not "
                   "observed farmer practice. Crop parameters are indicative and must be calibrated.",
    )


@app.errorhandler(BadRequest)
def _bad(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(ClimateError)
def _climate(e):
    return jsonify(error=str(e)), 502


@app.route("/")
def index():
    return send_file(os.path.join(BASE, "index.html"))


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/api/crops")
def api_crops():
    return jsonify({n: asdict(c) for n, c in CROPS.items()})


@app.route("/api/calendar")
def api_calendar():
    return jsonify(compute())


@app.route("/api/calendar.csv")
def api_calendar_csv():
    data = compute()
    cal = data["calendar"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["crop", "status", "score", "best_sowing", "best_harvest", "cycle_days", "sowing_window",
                "acceptable_window", "harvest_window", "reason"] + cal["months"])
    for c in cal["crops"]:
        w.writerow([c["crop"], c["status"], c["score"], c.get("best_sowing") or "", c.get("best_harvest") or "",
                    c["cycle_days"] or "", "; ".join(c["sowing_window"]), "; ".join(c["acceptable_window"]),
                    "; ".join(c["harvest_window"]), c["reason"]] + [m["code"] for m in c["months"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=crop_calendar.csv"})


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
