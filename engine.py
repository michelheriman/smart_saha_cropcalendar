"""
Crop calendar engine: climate-rule model (agro-climatic feasibility).

For every possible sowing day (1..365, wrapping over the year end) the engine
  1. finds cycle length (GDD accumulation or fixed length),
  2. rejects cycles that cannot mature or are hit by frost (10th percentile Tmin < tkill),
  3. scores temperature suitability, heat stress, photoperiod, water supply/demand,
     seedbed moisture and harvest weather,
then extracts recommended / acceptable sowing windows and the matching harvest window.
Perennials (grapes, citrus, pistachios, almond, apple, peach, walnut, avocado) use a phenology handler
(chilling, budbreak, GDD to harvest). Tropical trees and vines (coffee, cacao, mango, vanilla) use a
bloom-trigger handler (rain returning after a dry spell, or a cool/dry spell) plus a fixed bloom-to-harvest cycle.

Method references
-----------------
Allen et al. (1998) FAO-56; Doorenbos & Kassam (1979) FAO-33; Hargreaves & Samani (1985);
McMaster & Wilhelm (1997) GDD; Ramirez-Villegas et al. (2013) EcoCrop-type suitability;
Sacks et al. (2010) & Jagermeyr/Frieler (2018) for the concept of climate-limited growing seasons;
Winkler et al. (1974) / Jones et al. (2005) for grape heat summation.
"""
import numpy as np

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DIM = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
CUM = np.concatenate([[0], np.cumsum(DIM)])
MONTH_OF_DAY = np.repeat(np.arange(12), DIM)
N = 365

MIN_SCORE = 0.30     # below this a sowing date is not viable
GOOD_SCORE = 0.60    # best score above this -> "suitable", otherwise "marginal"
REC_FRAC = 0.85      # recommended window: score >= 85% of best
ACC_FRAC = 0.65      # acceptable window:  score >= 65% of best


# ------------------------------------------------------------------ helpers
def label(d):
    m = int(MONTH_OF_DAY[d % N])
    return f"{int(d % N - CUM[m] + 1):02d} {MONTHS[m]}"


def runs(mask):
    """Contiguous True runs on a circular 365-day mask -> list of (start, end) 0-based, inclusive."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    if m.all():
        return [(0, N - 1)]
    off = int(np.argmin(m))              # a False position
    r = np.roll(m, -off)
    out, i = [], 0
    while i < N:
        if r[i]:
            j = i
            while j + 1 < N and r[j + 1]:
                j += 1
            out.append(((i + off) % N, (j + off) % N))
            i = j + 1
        else:
            i += 1
    return sorted(out)


def windows(mask):
    res = []
    for a, b in runs(mask):
        res.append("year-round" if (a, b) == (0, N - 1) else f"{label(a)} - {label(b)}")
    return res


def dilate(mask, k):
    out = np.zeros(N, bool)
    for s in range(-k, k + 1):
        out |= np.roll(mask, s)
    return out


def trap(t, lo, o1, o2, hi):
    up = (t - lo) / max(o1 - lo, 1e-6)
    dn = (hi - t) / max(hi - o2, 1e-6)
    return np.clip(np.minimum(up, dn), 0, 1)


def month_cells(rec, acc, harv, grow):
    cells = []
    for m in range(12):
        sel = MONTH_OF_DAY == m
        sr, sa, h, g = rec[sel].mean(), acc[sel].mean(), harv[sel].mean(), grow[sel].mean()
        code = ""
        if sr >= 0.2:
            code += "S"
        elif sa >= 0.2:
            code += "s"
        if h >= 0.2:
            code += "H"
        if not code and g >= 0.2:
            code = "g"
        cells.append(dict(code=code, sow=round(float(sr), 2), harvest=round(float(h), 2), grow=round(float(g), 2)))
    return cells


def _empty_months():
    return [dict(code="", sow=0.0, harvest=0.0, grow=0.0) for _ in range(12)]


def _fail(crop, reason, extra=None):
    r = dict(crop=crop.name, group=crop.group, kind=crop.kind, status="not_suitable", score=0.0,
             best_sowing=None, sowing_window=[], acceptable_window=[], harvest_window=[],
             cycle_days=None, reason=reason, limiting_factors={}, months=_empty_months(),
             phenology={}, note=crop.note)
    if extra:
        r.update(extra)
    return r


# ------------------------------------------------------------------ annual crops
def _annual(crop, c, irrigated):
    tile = lambda a: np.tile(a, 3)
    tm3, tlo3, thi3, p3, et3, dl3 = map(tile, (c.tmean, c.tmin_lo, c.tmax_hi, c.p, c.et0, c.daylen))

    if crop.cycle_days:
        L = np.full(N, int(crop.cycle_days))
    else:
        gdd_d = np.clip(c.tmean - crop.tbase, 0, max(crop.topt_hi - crop.tbase, 0))
        g3 = tile(gdd_d)
        C = np.cumsum(g3)
        Cprev = C - g3
        idx = np.searchsorted(C, Cprev[:N] + crop.gdd, side="left")
        L = idx - np.arange(N) + 1

    mature = L <= crop.max_cycle
    frost = np.zeros(N, bool)
    names = ("temp", "heat", "photo", "water", "est", "harv")
    f = {k: np.zeros(N) for k in names}
    score = np.zeros(N)

    for s in range(N):
        if not mature[s]:
            continue
        Ls = int(L[s])
        e = s + Ls
        if tlo3[s:e].min() < crop.tkill:
            frost[s] = True
            continue
        seg = slice(s, e)
        ft = trap(tm3[seg], crop.tbase, crop.topt_lo, crop.topt_hi, crop.tmax).mean()

        fh = 1.0
        if crop.heat_tmax is not None:
            a = s + int(crop.heat_phase[0] * Ls)
            b = max(s + int(crop.heat_phase[1] * Ls), a + 1)
            fh = max(0.0, 1 - np.maximum(thi3[a:b] - crop.heat_tmax, 0).mean() / 5.0)

        fp = 1.0
        if crop.dl_min is not None or crop.dl_max is not None:
            a = s + int(crop.dl_phase[0] * Ls)
            b = max(s + int(crop.dl_phase[1] * Ls), a + 1)
            m = dl3[a:b].mean()
            if crop.dl_min is not None:
                fp *= float(np.clip(1 - max(crop.dl_min - m, 0) / 2.0, 0, 1))
            if crop.dl_max is not None:
                fp *= float(np.clip(1 - max(m - crop.dl_max, 0) / 2.0, 0, 1))

        fw = fe = 1.0
        if not irrigated:
            etc = (crop.kc * et3[seg] + crop.extra_mm).sum()
            ratio = 0.8 * p3[seg].sum() / max(etc, 1e-6)                    # effective rain / demand
            fw = float(np.clip(1 - crop.ky * (1 - min(ratio, 1.0)), 0, 1))  # FAO-33 linear response
            s14 = slice(s, s + 14)
            r14 = 0.8 * p3[s14].sum() / max((0.5 * crop.kc * et3[s14] + crop.extra_mm).sum(), 1e-6)
            fe = float(np.clip(r14 / 0.6, 0.35, 1.0))                       # seedbed moisture

        fhv = 1.0
        if crop.dry_harvest:
            fhv = float(np.clip(1 - 0.12 * p3[e - 15:e].mean(), 0.4, 1.0))

        vals = dict(temp=ft, heat=fh, photo=fp, water=fw, est=fe, harv=fhv)
        for k, v in vals.items():
            f[k][s] = v
        score[s] = ft * fh * fp * fw * fe * fhv

    best_day = int(np.argmax(score))
    best = float(score[best_day])

    if best < MIN_SCORE:
        feas = mature & ~frost
        if not mature.any():
            reason = "Too cool: the GDD target is never reached within the maximum cycle length."
        elif not feas.any():
            reason = "Frost (10th-percentile Tmin below the lethal limit) hits every possible cycle."
        else:
            means = {k: float(f[k][feas].mean()) for k in names}
            worst = min(means, key=means.get)
            text = {"temp": "temperature far from the crop optimum", "heat": "heat stress at the sensitive stage",
                    "photo": "unfavourable day length", "water": "water deficit under rainfed conditions "
                    "(try irrigated=true)", "est": "dry seedbed at establishment", "harv": "wet weather at harvest"}
            reason = f"Main limitation: {text[worst]}."
        return _fail(crop, reason)

    rec = score >= max(MIN_SCORE, REC_FRAC * best)
    acc = score >= max(MIN_SCORE, ACC_FRAC * best)
    harv = np.zeros(N, bool)
    for s in np.where(rec)[0]:
        harv[(s + int(L[s]) - 1) % N] = True
    harv = dilate(harv, 2)
    Lb = int(L[best_day])
    grow = np.zeros(N, bool)
    grow[(best_day + np.arange(Lb)) % N] = True

    return dict(crop=crop.name, group=crop.group, kind=crop.kind,
                status="suitable" if best >= GOOD_SCORE else "marginal", score=round(best, 2),
                best_sowing=label(best_day), best_harvest=label(best_day + Lb - 1),
                sowing_window=windows(rec), acceptable_window=windows(acc), harvest_window=windows(harv),
                cycle_days=Lb, reason="", limiting_factors={k: round(float(f[k][best_day]), 2) for k in names},
                months=month_cells(rec, acc, harv, grow), phenology={}, note=crop.note)


# ------------------------------------------------------------------ perennial crops
def _chill_hours(tmax, tmin, lo=0.0, hi=7.2):
    h = np.arange(24)[:, None]
    T = (tmax + tmin)[None, :] / 2 + (tmax - tmin)[None, :] / 2 * np.sin(2 * np.pi * (h - 9) / 24)
    return ((T >= lo) & (T <= hi)).sum(axis=0).astype(float)


def _perennial(crop, c, irrigated):
    tm = c.tmean
    cold = int(np.argmin(tm))
    pheno = {}

    if crop.winter_tkill is not None and c.tmin_lo.min() < crop.winter_tkill:
        return _fail(crop, f"Winter minima (10th percentile {c.tmin_lo.min():.1f} C) exceed the hardiness "
                           f"limit of {crop.winter_tkill} C.")

    chill_f = 1.0
    k_start = 1
    if crop.chill_h > 0:
        win = (cold + np.arange(-100, 101)) % N
        chill = float(_chill_hours(c.tmax, c.tmin)[win].sum())
        pheno["chilling_hours"] = round(chill)
        chill_f = min(1.0, chill / crop.chill_h)
        if chill_f < 0.6:
            return _fail(crop, f"Insufficient chilling: ~{chill:.0f} h available vs ~{crop.chill_h:.0f} h required.",
                         dict(phenology=pheno))
        # dormancy release: budbreak is allowed only once the chilling requirement is accumulated
        # (if it is never fully met, release is delayed to the end of the chilling window)
        cum = np.cumsum(_chill_hours(c.tmax, c.tmin)[win])
        reached = np.where(cum >= crop.chill_h)[0]
        k_start = max(1, int(reached[0]) - 100 + 1) if len(reached) else 101

    bud = None
    bud_t = crop.bud_temp if crop.bud_temp is not None else crop.tbase
    for k in range(k_start, 201):
        d = (cold + k) % N
        if tm[d] >= bud_t and c.tmin_lo[(d + np.arange(14)) % N].min() >= crop.tkill:
            bud = d
            break
    if bud is None:
        return _fail(crop, "No frost-free spring warm enough for budbreak.", dict(phenology=pheno))

    gdd_d = np.clip(tm - crop.tbase, 0, max(crop.topt_hi - crop.tbase, 0))
    g3 = np.tile(gdd_d, 3)
    C = np.cumsum(g3)
    L = int(np.searchsorted(C, C[bud] - g3[bud] + crop.gdd, side="left") - bud + 1)
    if L > crop.max_cycle:
        return _fail(crop, "Insufficient heat accumulation between budbreak and fruit maturity.",
                     dict(phenology=pheno))

    idx = (bud + np.arange(L)) % N
    ft = float(trap(tm[idx], crop.tbase, crop.topt_lo, crop.topt_hi, crop.tmax).mean())
    fh = 1.0
    if crop.heat_tmax is not None:
        a, b = int(crop.heat_phase[0] * L), max(int(crop.heat_phase[1] * L), int(crop.heat_phase[0] * L) + 1)
        fh = max(0.0, 1 - np.maximum(c.tmax_hi[idx[a:b]] - crop.heat_tmax, 0).mean() / 5.0)
    fh = float(fh)
    fw = 1.0
    if not irrigated:
        # deep-rooted trees also use water stored from the rain of the 120 days before bloom (half counted)
        stored = 0.5 * float(c.p[(bud - np.arange(1, 121)) % N].sum())
        ratio = 0.8 * (float(c.p[idx].sum()) + stored) / max(float((crop.kc * c.et0[idx]).sum()), 1e-6)
        fw = float(np.clip(1 - crop.ky * (1 - min(ratio, 1.0)), 0, 1))
    fhv = 1.0
    if crop.dry_harvest:
        fhv = float(np.clip(1 - 0.12 * c.p[idx[-15:]].mean(), 0.4, 1.0))
    score = ft * fh * fw * fhv * chill_f
    if score < MIN_SCORE:
        return _fail(crop, "Climate suitability too low (temperature/heat/water combination).",
                     dict(phenology=pheno, limiting_factors=dict(temp=round(ft, 2), heat=round(fh, 2),
                                                                  water=round(fw, 2), chill=round(chill_f, 2))))

    pheno.update(budbreak_bloom=label(bud), harvest=label(bud + L - 1))
    if float(tm.max() - tm.min()) < 4.0:
        pheno["warning"] = ("Weak thermal seasonality: flowering is driven by dry spells / irrigation; "
                            "dates are only indicative.")

    plant = np.zeros(N, bool)
    span = np.arange(0, 61) if crop.plant_after_budbreak else np.arange(-45, 0)
    plant[(bud + span) % N] = True
    harv = np.zeros(N, bool)
    harv[(bud + L - 1 + np.arange(-14, 15)) % N] = True
    grow = np.zeros(N, bool)
    grow[idx] = True
    bud_mask = np.zeros(N, bool)
    bud_mask[(bud + np.arange(-7, 8)) % N] = True

    cells = month_cells(plant, plant, harv, grow)
    for m, cell in enumerate(cells):                      # mark bloom/budbreak month with 'B'
        if bud_mask[MONTH_OF_DAY == m].mean() >= 0.2 and "B" not in cell["code"]:
            cell["code"] += "B"

    return dict(crop=crop.name, group=crop.group, kind=crop.kind,
                status="suitable" if score >= GOOD_SCORE else "marginal", score=round(float(score), 2),
                best_sowing=f"{label(bud + span[0])} (planting)", best_harvest=label(bud + L - 1),
                sowing_window=windows(plant), acceptable_window=windows(plant), harvest_window=windows(harv),
                cycle_days=L, reason="",
                limiting_factors=dict(temp=round(ft, 2), heat=round(fh, 2), water=round(fw, 2),
                                      harv=round(fhv, 2), chill=round(chill_f, 2)),
                months=cells, phenology=pheno, note=crop.note)


# ------------------------------------------------------------------ tropical trees / vines
def _circ_sum(a, w):
    """Sum of `a` over the w days starting at each day (circular, length N)."""
    ext = np.concatenate([a, a[:w - 1]])
    cs = np.concatenate([[0.0], np.cumsum(ext)])
    return cs[w:] - cs[:-w]


def _z(a):
    s = float(np.std(a))
    return (a - float(np.mean(a))) / s if s > 1e-9 else np.zeros_like(a)


def _band(day, back, fwd):
    m = np.zeros(N, bool)
    m[(day + np.arange(-back, fwd + 1)) % N] = True
    return m


def _tropical_tree(crop, c, irrigated):
    """Evergreen tropical tree/vine: whole-year climate suitability + bloom trigger + fixed cycle."""
    tm = c.tmean
    pheno = {}
    if c.tmin_lo.min() < crop.tkill:
        return _fail(crop, f"Cold limit: the 10th-percentile Tmin reaches {c.tmin_lo.min():.1f} C, "
                           f"below the {crop.tkill} C tolerance.")
    ft = float(trap(tm, crop.tbase, crop.topt_lo, crop.topt_hi, crop.tmax).mean())
    fh = 1.0
    if crop.heat_tmax is not None:
        fh = max(0.0, 1 - float(np.maximum(c.tmax_hi - crop.heat_tmax, 0).mean()) / 5.0)
    monthly = np.array([c.p[CUM[m]:CUM[m + 1]].sum() for m in range(12)])
    n_dry = int((monthly < crop.dry_mm).sum())
    fw = fd = 1.0
    if not irrigated:
        ratio = 0.8 * float(c.p.sum()) / max(crop.kc * float(c.et0.sum()), 1e-6)
        fw = float(np.clip(1 - crop.ky * (1 - min(ratio, 1.0)), 0, 1))
        fd = max(0.0, 1 - 0.25 * max(n_dry - crop.dry_max_months, 0))
        fd *= max(0.0, 1 - 0.25 * max(crop.dry_min_months - n_dry, 0))
    factors = dict(temp=round(ft, 2), heat=round(fh, 2), water=round(fw, 2), dry_season=round(fd, 2))
    pheno["dry_months"] = n_dry
    score = ft * fh * fw * fd
    if score < MIN_SCORE:
        worst = min(factors, key=factors.get)
        text = {"temp": "annual temperature far from the crop optimum", "heat": "heat stress",
                "water": "annual rainfall too low for rainfed culture (try irrigated=true)",
                "dry_season": "dry season too long or too short for the crop"}
        return _fail(crop, f"Main limitation: {text[worst]}.", dict(limiting_factors=factors, phenology=pheno))

    p60 = _circ_sum(c.p, 60)
    seasonal = bool(p60.min() < 0.4 * p60.mean())
    dry_end = (int(np.argmin(p60)) + 60) % N
    wet_start = int(np.argmax(_circ_sum(c.p, 90)))
    onset = dry_end if seasonal else wet_start            # planting at the start of the rains
    warn = []
    if crop.bloom_trigger == "dry_cool":
        idx = int(np.argmin(_z(p60) + _z(_circ_sum(tm, 60) / 60.0)))
        bloom = (idx + 45) % N
        if not seasonal and float(tm.max() - tm.min()) < 2.0:
            warn.append("No marked cool or dry spell: flowering would be weak or irregular; the date shown "
                        "is only the relatively coolest and driest period.")
    elif seasonal:
        bloom = dry_end
    else:
        bloom = wet_start
        warn.append("No marked dry season: flowering and harvest are spread through the year; the dates "
                    "mark the main flush only.")
    harvest_day = (bloom + int(crop.cycle_days)) % N

    plant = _band(onset, 0, 44)
    harv = _band(harvest_day, 21, 21)
    grow = np.zeros(N, bool)
    grow[(bloom + np.arange(int(crop.cycle_days))) % N] = True
    bloom_m = _band(bloom, 10, 10)
    cells = month_cells(plant, plant, harv, grow)
    for m, cell in enumerate(cells):
        if bloom_m[MONTH_OF_DAY == m].mean() >= 0.2 and "B" not in cell["code"]:
            cell["code"] += "B"
    pheno.update(trigger=crop.bloom_trigger, bloom=label(bloom), harvest=label(harvest_day))
    if warn:
        pheno["warning"] = " ".join(warn)

    return dict(crop=crop.name, group=crop.group, kind=crop.kind,
                status="suitable" if score >= GOOD_SCORE else "marginal", score=round(float(score), 2),
                best_sowing=f"{label(onset)} (planting)", best_harvest=label(harvest_day),
                sowing_window=windows(plant), acceptable_window=windows(plant), harvest_window=windows(harv),
                cycle_days=int(crop.cycle_days), reason="", limiting_factors=factors,
                months=cells, phenology=pheno, note=crop.note)


# ------------------------------------------------------------------ public API
def run_calendar(clim, crops, irrigated=False, start_month=1):
    results = []
    for crop in crops:
        if crop.kind == "perennial":
            res = _perennial(crop, clim, irrigated)
        elif crop.kind == "tropical_tree":
            res = _tropical_tree(crop, clim, irrigated)
        else:
            res = _annual(crop, clim, irrigated)
        results.append(res)
    r = (start_month - 1) % 12
    month_names = MONTHS[r:] + MONTHS[:r]
    for res in results:
        res["months"] = res["months"][r:] + res["months"][:r]
    return dict(months=month_names, crops=results)
