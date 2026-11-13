"""
Crop parameter table.

IMPORTANT: the numbers below are INDICATIVE STARTING VALUES written from general
agronomic knowledge. They are NOT copied from a database. Before any serious use,
check and calibrate them against:
  - FAO EcoCrop database (temperature / rainfall ranges, cycle length)
  - FAO-56 (Allen et al., 1998), Table 12 (Kc, stage lengths)
  - Doorenbos & Kassam (1979), FAO-33 (yield response factor Ky)
  - local cultivar data (maturity class, photoperiod type)

You can override any value at request time with ?overrides={"maize":{"gdd":1700}}
or edit this file directly.

Fields
------
kind            "annual" (sow -> harvest), "perennial" (tree: chilling, budbreak, GDD to
                harvest) or "tropical_tree" (bloom trigger + fixed cycle, see below)
tbase           base temperature for GDD (deg C)
topt_lo/hi      optimum range of daily mean temperature (deg C); GDD capped at topt_hi
tmax            absolute upper temperature limit for growth (deg C)
tkill           lethal minimum temperature; compared with the 10th-percentile daily
                minimum (a frost-risk proxy). For perennials it is the spring-frost
                limit after budbreak.
gdd             thermal time sowing -> maturity/harvest (deg C day, base tbase)
cycle_days      fixed cycle length (used instead of gdd, e.g. cassava, pineapple)
max_cycle       cycles longer than this are rejected (days)
kc              mean crop coefficient over the cycle
ky              yield response factor to water deficit (FAO-33)
extra_mm        extra water demand, mm/day (e.g. rice percolation / flooding)
heat_tmax       daytime max temperature above which heat stress occurs
heat_phase      sensitive phase as (start, end) fractions of the cycle
dl_min/dl_max   day-length limits (hours) in dl_phase (bulbing, bolting, flowering...)
dry_harvest     crop needs dry weather at harvest (grain, curing, cotton...)
chill_h         chilling requirement (hours 0-7.2 C) for perennials
winter_tkill    winter hardiness limit for perennials
plant_after_budbreak  planting of new orchard after budbreak (evergreen) instead of
                dormant-season planting
bud_temp        daily mean temperature that triggers budbreak (default: tbase)
bloom_trigger   tropical trees: "rain_after_dry" (bloom when rains return after the
                driest 60 days) or "dry_cool" (bloom after the coolest and driest 60 days)
dry_mm          monthly rainfall below which a month counts as dry (tropical trees)
dry_min_months  months below dry_mm needed to induce flowering (rainfed, tropical trees)
dry_max_months  months below dry_mm tolerated before suitability falls (rainfed)

kind "tropical_tree" = evergreen tropical tree or vine with a fixed bloom-to-harvest
cycle (cycle_days): cacao, coffee, mango, vanilla.
"""
from dataclasses import dataclass, fields, replace
from typing import Optional, Tuple, Dict


@dataclass(frozen=True)
class Crop:
    name: str
    kind: str
    tbase: float
    topt_lo: float
    topt_hi: float
    tmax: float
    tkill: float
    gdd: Optional[float] = None
    cycle_days: Optional[int] = None
    max_cycle: int = 400
    kc: float = 1.0
    ky: float = 1.0
    extra_mm: float = 0.0
    heat_tmax: Optional[float] = None
    heat_phase: Tuple[float, float] = (0.4, 0.7)
    dl_min: Optional[float] = None
    dl_max: Optional[float] = None
    dl_phase: Tuple[float, float] = (0.4, 0.8)
    dry_harvest: bool = False
    chill_h: float = 0.0
    winter_tkill: Optional[float] = None
    plant_after_budbreak: bool = False
    bud_temp: Optional[float] = None
    bloom_trigger: str = "warm_up"
    dry_mm: float = 60.0
    dry_min_months: int = 0
    dry_max_months: int = 12
    group: str = ""
    note: str = ""


def _c(name, **kw):
    return name, Crop(name=name, **kw)


CROPS: Dict[str, Crop] = dict([
    # ---------------- vegetables / roots ----------------
    _c("onion", kind="annual", group="vegetable", tbase=4, topt_lo=12, topt_hi=24, tmax=35,
       tkill=-5, gdd=1500, kc=0.85, ky=1.1, heat_tmax=35, heat_phase=(0.5, 0.9),
       dl_min=12.5, dl_phase=(0.45, 0.8), dry_harvest=True,
       note="Bulbing is photoperiod-driven and cultivar dependent: short-day ~11-12 h, "
            "intermediate ~12-13 h, long-day ~14-16 h. Override dl_min for your cultivar."),
    _c("potato", kind="annual", group="vegetable", tbase=4, topt_lo=14, topt_hi=22, tmax=30,
       tkill=-1.5, gdd=1300, kc=1.0, ky=1.1, heat_tmax=30, heat_phase=(0.3, 0.8),
       note="Tuber bulking is strongly reduced when day temperatures stay above ~30 C."),
    _c("carrots", kind="annual", group="vegetable", tbase=4, topt_lo=14, topt_hi=22, tmax=30,
       tkill=-4, gdd=1300, kc=0.9, ky=1.0, heat_tmax=30, heat_phase=(0.4, 0.9)),
    _c("celery", kind="annual", group="vegetable", tbase=5, topt_lo=15, topt_hi=21, tmax=28,
       tkill=-2, gdd=1300, kc=1.0, ky=1.1, heat_tmax=28, heat_phase=(0.5, 0.95),
       note="Dates refer to field establishment; add ~8-10 weeks for nursery."),
    _c("lettuce", kind="annual", group="vegetable", tbase=4, topt_lo=12, topt_hi=20, tmax=27,
       tkill=-3, gdd=700, kc=0.9, ky=1.0, heat_tmax=28, heat_phase=(0.6, 1.0),
       dl_max=14.5, dl_phase=(0.6, 1.0),
       note="Heat and long days trigger bolting."),
    _c("spinach", kind="annual", group="vegetable", tbase=2, topt_lo=10, topt_hi=20, tmax=28,
       tkill=-8, gdd=600, kc=0.95, ky=1.0, heat_tmax=27, heat_phase=(0.5, 1.0),
       dl_max=14.0, dl_phase=(0.5, 1.0), note="Long days (>~14 h) trigger bolting."),
    _c("radish", kind="annual", group="vegetable", tbase=4, topt_lo=10, topt_hi=22, tmax=28,
       tkill=-3, gdd=450, kc=0.85, ky=0.9, heat_tmax=28, heat_phase=(0.4, 1.0),
       dl_max=14.0, dl_phase=(0.4, 1.0)),
    _c("eggplant", kind="annual", group="vegetable", tbase=12, topt_lo=22, topt_hi=30, tmax=38,
       tkill=2, gdd=1700, kc=1.0, ky=1.1, heat_tmax=35, heat_phase=(0.4, 0.8),
       note="Dates refer to field transplanting."),
    _c("tomato", kind="annual", group="vegetable", tbase=10, topt_lo=20, topt_hi=27, tmax=35,
       tkill=1, gdd=1600, kc=1.0, ky=1.05, heat_tmax=32, heat_phase=(0.4, 0.7),
       note="Fruit set drops when day temperature exceeds ~32 C. Dates refer to transplanting."),
    _c("sweet potato", kind="annual", group="root", tbase=12, topt_lo=22, topt_hi=30, tmax=38,
       tkill=2, gdd=1700, kc=0.9, ky=0.9, heat_tmax=38, heat_phase=(0.4, 0.9)),
    _c("cassava", kind="annual", group="root", tbase=14, topt_lo=22, topt_hi=30, tmax=38,
       tkill=3, cycle_days=300, max_cycle=450, kc=0.8, ky=0.5, heat_tmax=38,
       note="Fixed 10-month cycle assumed; 8-18 months depending on cultivar and altitude."),
    # ---------------- legumes ----------------
    _c("beans green", kind="annual", group="legume", tbase=10, topt_lo=18, topt_hi=27, tmax=33,
       tkill=1, gdd=800, kc=0.9, ky=1.15, heat_tmax=32, heat_phase=(0.4, 0.7)),
    _c("beans", kind="annual", group="legume", tbase=10, topt_lo=18, topt_hi=26, tmax=32,
       tkill=1, gdd=1100, kc=0.85, ky=1.15, heat_tmax=32, heat_phase=(0.4, 0.7),
       dry_harvest=True, note="Dry beans."),
    _c("peas", kind="annual", group="legume", tbase=4, topt_lo=13, topt_hi=20, tmax=28,
       tkill=-4, gdd=1200, kc=1.0, ky=1.15, heat_tmax=27, heat_phase=(0.4, 0.7)),
    _c("soybeans", kind="annual", group="legume", tbase=10, topt_lo=22, topt_hi=30, tmax=38,
       tkill=0, gdd=1800, kc=0.95, ky=0.85, heat_tmax=36, heat_phase=(0.4, 0.7),
       dl_max=14.5, dl_phase=(0.2, 0.5), dry_harvest=True,
       note="Short-day plant; tropical cultivars are less sensitive. Override dl_max."),
    # ---------------- cereals / oil / fibre ----------------
    _c("maize", kind="annual", group="cereal", tbase=8, topt_lo=20, topt_hi=30, tmax=38,
       tkill=0, gdd=1500, kc=0.95, ky=1.25, heat_tmax=35, heat_phase=(0.45, 0.6),
       dry_harvest=True),
    _c("rice", kind="annual", group="cereal", tbase=10, topt_lo=25, topt_hi=32, tmax=38,
       tkill=4, gdd=2000, kc=1.1, ky=1.1, extra_mm=5.0, heat_tmax=35, heat_phase=(0.5, 0.65),
       dry_harvest=True, note="Flooded paddy: extra 5 mm/day for percolation/seepage assumed."),
    _c("millet", kind="annual", group="cereal", tbase=10, topt_lo=25, topt_hi=35, tmax=42,
       tkill=1, gdd=1500, kc=0.8, ky=0.6, heat_tmax=40, heat_phase=(0.4, 0.6),
       dry_harvest=True, note="Pearl millet."),
    _c("sorghum", kind="annual", group="cereal", tbase=8, topt_lo=24, topt_hi=33, tmax=40,
       tkill=1, gdd=1900, kc=0.85, ky=0.9, heat_tmax=38, heat_phase=(0.45, 0.65),
       dry_harvest=True),
    _c("cotton", kind="annual", group="fibre", tbase=15, topt_lo=22, topt_hi=32, tmax=38,
       tkill=2, gdd=1600, max_cycle=300, kc=0.95, ky=0.85, heat_tmax=36, heat_phase=(0.4, 0.7),
       dry_harvest=True),
    _c("sesame", kind="annual", group="oil", tbase=12, topt_lo=24, topt_hi=32, tmax=40,
       tkill=2, gdd=1500, kc=0.85, ky=0.7, heat_tmax=38, heat_phase=(0.4, 0.7),
       dry_harvest=True),
    _c("sunflower", kind="annual", group="oil", tbase=6, topt_lo=18, topt_hi=27, tmax=36,
       tkill=-2, gdd=1700, kc=0.85, ky=0.95, heat_tmax=35, heat_phase=(0.45, 0.65),
       dry_harvest=True),
    # ---------------- long-cycle / perennial ----------------
    _c("pineapple", kind="annual", group="fruit", tbase=15, topt_lo=22, topt_hi=30, tmax=35,
       tkill=5, cycle_days=540, max_cycle=700, kc=0.45, ky=0.4,
       note="Planting to first harvest ~15-20 months. Frost-free, low-chill sites only."),
    _c("grapes", kind="perennial", group="fruit", tbase=10, topt_lo=20, topt_hi=30, tmax=40,
       tkill=-1.5, gdd=1600, max_cycle=330, kc=0.6, ky=0.85, heat_tmax=38, heat_phase=(0.4, 0.8),
       chill_h=100, winter_tkill=-15, bud_temp=12, dry_harvest=True,
       note="Budbreak -> harvest by GDD (Winkler-type). Planting window = dormant season. "
            "Low-chill table varieties can be grown with chill_h lowered."),
    _c("citrus", kind="perennial", group="fruit", tbase=13, topt_lo=23, topt_hi=30, tmax=38,
       tkill=-2, gdd=1700, max_cycle=400, kc=0.65, ky=0.9, heat_tmax=38, heat_phase=(0.2, 0.5),
       winter_tkill=-6, plant_after_budbreak=True,
       note="Bloom -> maturity by GDD (varies strongly with species: 6-12+ months). "
            "In weakly seasonal tropics flowering is driven by dry spells; dates are indicative."),
    _c("pistachios", kind="perennial", group="fruit", tbase=10, topt_lo=22, topt_hi=35, tmax=45,
       tkill=-2, gdd=2500, max_cycle=330, kc=0.75, ky=0.5, heat_tmax=44, heat_phase=(0.3, 0.7),
       chill_h=800, winter_tkill=-15, dry_harvest=True,
       note="Needs ~800-1000 chilling hours (cultivar dependent) and long hot summers."),
    # ---------------- temperate / subtropical tree crops (deciduous or evergreen) ----------------
    # gdd = thermal time from budbreak/bloom to harvest; all values are indicative.
    _c("almond", kind="perennial", group="tree", tbase=10, topt_lo=20, topt_hi=32, tmax=40,
       tkill=-2, gdd=2200, max_cycle=280, kc=0.9, ky=0.8, heat_tmax=38, heat_phase=(0.3, 0.7),
       chill_h=400, winter_tkill=-15, bud_temp=9, dry_harvest=True,
       note="Blooms early: spring frost at bloom is the main risk (tkill applies after budbreak). "
            "Chilling need is cultivar dependent (~200-700 h). Needs a long, hot, dry summer."),
    _c("apple", kind="perennial", group="tree", tbase=5, topt_lo=15, topt_hi=24, tmax=33,
       tkill=-2, gdd=1700, max_cycle=260, kc=0.95, ky=1.0, heat_tmax=33, heat_phase=(0.5, 0.9),
       chill_h=1000, winter_tkill=-25, bud_temp=7,
       note="Chilling need ~300 h (low-chill cultivars) to 1500 h; set chill_h for your cultivar. "
            "Hot nights and sunburn above ~33 C lower quality."),
    _c("peach", kind="perennial", group="tree", tbase=7, topt_lo=18, topt_hi=28, tmax=38,
       tkill=-2, gdd=1800, max_cycle=250, kc=0.9, ky=1.0, heat_tmax=36, heat_phase=(0.5, 0.9),
       chill_h=600, winter_tkill=-20, bud_temp=9,
       note="Chilling need ~100 h (low-chill) to 1000 h. Bloom-to-harvest time varies from 3 to 6 months "
            "with cultivar earliness; adjust gdd."),
    _c("walnut", kind="perennial", group="tree", tbase=10, topt_lo=18, topt_hi=30, tmax=38,
       tkill=-2, gdd=1500, max_cycle=260, kc=1.1, ky=0.9, heat_tmax=36, heat_phase=(0.4, 0.8),
       chill_h=700, winter_tkill=-20, bud_temp=10, dry_harvest=True,
       note="Persian walnut. Late spring frost damages flowers and shoots; chilling ~400-1500 h by cultivar. "
            "Bloom-to-harvest heat need runs from ~1300 (late-leafing, cool sites) to ~2100 (warm sites); adjust gdd."),
    _c("avocado", kind="perennial", group="tree", tbase=10, topt_lo=20, topt_hi=28, tmax=35,
       tkill=-1, gdd=2700, max_cycle=450, kc=0.85, ky=0.8, heat_tmax=35, heat_phase=(0.0, 0.3),
       winter_tkill=-3, bud_temp=14, plant_after_budbreak=True,
       note="Evergreen, frost-sensitive (Hass ~ -2 C). Bloom-to-harvest is 6-12+ months by cultivar and "
            "altitude. In weakly seasonal tropics flowering is spread out; dates are indicative."),
    # ---------------- annual-style crops ----------------
    _c("strawberry", kind="annual", group="fruit", tbase=5, topt_lo=12, topt_hi=22, tmax=30,
       tkill=-8, gdd=1300, kc=0.85, ky=1.0, heat_tmax=28, heat_phase=(0.4, 1.0),
       note="Dates refer to planting of runner plants and the first fruiting season. tkill is set for "
            "hardened plants; flowers are damaged by frost near 0 C."),
    _c("sugarcane", kind="annual", group="sugar", tbase=12, topt_lo=24, topt_hi=34, tmax=40,
       tkill=0, cycle_days=365, max_cycle=540, kc=0.9, ky=1.2, heat_tmax=40, dry_harvest=True,
       note="Plant cane with a 12-month cycle assumed (10-18 months by region). Ratoon crops follow the "
            "same calendar. Ripening needs a cooler or drier spell, which is not modelled."),
    # ---------------- tropical trees and vines (kind = tropical_tree) ----------------
    _c("coffee", kind="tropical_tree", group="tree", tbase=10, topt_lo=17, topt_hi=22, tmax=28,
       tkill=1, cycle_days=240, kc=1.0, ky=1.0, heat_tmax=30, bloom_trigger="rain_after_dry",
       dry_mm=60, dry_max_months=4, dry_harvest=True,
       note="Arabica assumed (optimum annual mean 18-22 C, frost-sensitive). Blooms when rains return after "
            "a dry spell; about 8 months to ripe cherry. For robusta override tbase=12, topt_lo=22, "
            "topt_hi=30, tmax=34, cycle_days=300."),
    _c("cacao", kind="tropical_tree", group="tree", tbase=15, topt_lo=22, topt_hi=28, tmax=33,
       tkill=8, cycle_days=165, kc=1.0, ky=1.0, heat_tmax=33, bloom_trigger="rain_after_dry",
       dry_mm=100, dry_max_months=3,
       note="Needs about 1250+ mm rain, at most ~3 months below 100 mm, no cold below ~10 C and usually "
            "altitude below ~1000 m. Flowers all year: dates mark the main flush and the main pod crop "
            "~5-6 months later; a smaller second crop is common."),
    _c("mango", kind="tropical_tree", group="tree", tbase=10, topt_lo=24, topt_hi=30, tmax=40,
       tkill=1, cycle_days=130, kc=0.85, ky=0.9, heat_tmax=40, bloom_trigger="dry_cool",
       dry_mm=60, dry_max_months=8,
       note="Flowering is induced by a cool and/or dry spell of about 2 months; rain at bloom ruins fruit "
            "set. Bloom to ripe fruit is ~100-150 days by cultivar."),
    _c("vanilla", kind="tropical_tree", group="tree", tbase=15, topt_lo=21, topt_hi=30, tmax=35,
       tkill=8, cycle_days=270, kc=1.0, ky=1.0, heat_tmax=35, bloom_trigger="dry_cool",
       dry_mm=60, dry_max_months=4,
       note="Shaded vine on supports. Flowering follows a cooler, drier spell of about 2-3 months; "
            "pollination is by hand; pods mature ~8-9 months later, then curing. Rain ~1500-3000 mm."),
])

CROP_NAMES = list(CROPS.keys())
_FIELDS = {f.name for f in fields(Crop)}

# Accepted spellings that map to a canonical crop name.
ALIASES = {
    "grapewine": "grapes", "grapevine": "grapes", "grape": "grapes", "vine": "grapes",
    "carrot": "carrots", "pistachio": "pistachios", "green beans": "beans green",
    "green bean": "beans green", "dry beans": "beans", "common beans": "beans",
    "soybean": "soybeans", "soy": "soybeans", "sweetpotato": "sweet potato",
    "pea": "peas", "potatoes": "potato", "tomatoes": "tomato", "onions": "onion",
    "aubergine": "eggplant", "almonds": "almond", "apples": "apple", "avocados": "avocado",
    "mangoes": "mango", "mangos": "mango", "peaches": "peach", "walnuts": "walnut",
    "strawberries": "strawberry", "cocoa": "cacao", "orange": "citrus", "lemon": "citrus",
    "oranges": "citrus", "coffee arabica": "coffee",
}


def resolve(name):
    """Normalise a crop name (case, spaces, hyphens) and map aliases to canonical names."""
    n = " ".join(str(name).strip().lower().replace("-", " ").replace("_", " ").split())
    return ALIASES.get(n, n)


def merged_crops(names=None, overrides=None):
    """Return list of Crop with optional name filter and parameter overrides."""
    names = list(dict.fromkeys(resolve(n) for n in names)) if names else CROP_NAMES
    overrides = {resolve(k): v for k, v in (overrides or {}).items()}
    unknown = [k for k in overrides if k not in CROPS]
    if unknown:
        raise ValueError(f"Overrides given for unknown crop(s): {unknown}. Valid: {', '.join(CROP_NAMES)}")
    out = []
    for n in names:
        if n not in CROPS:
            raise ValueError(f"Unknown crop '{n}'. Valid: {', '.join(CROP_NAMES)}")
        crop = CROPS[n]
        ov = overrides.get(n)
        if ov:
            bad = set(ov) - _FIELDS
            if bad:
                raise ValueError(f"Unknown parameter(s) for {n}: {sorted(bad)}")
            ov = {k: (tuple(v) if isinstance(v, list) else v) for k, v in ov.items()}
            crop = replace(crop, **ov)
        out.append(crop)
    return out
