# Crop calendar from coordinates (Flask)

Agro-climatic sowing / harvest windows for 37 crops from a latitude/longitude.

Crops: onion, potato, carrots, maize, celery, lettuce, spinach, radish, eggplant, tomato, sweet potato,
cassava, beans green, beans, peas, soybeans, cotton, sesame, sunflower, millet, sorghum, rice, pineapple,
grapes (alias grapewine), citrus, pistachios, almond, apple, avocado, cacao, coffee, mango, peach,
strawberry, sugarcane, vanilla, walnut. Names are case-insensitive; aliases such as carrot, green beans,
cocoa are accepted.

Crop kinds: `annual` (sowing-date scan), `perennial` (chilling, dormancy release, budbreak, GDD to harvest:
grapes, citrus, pistachios, almond, apple, peach, walnut, avocado) and `tropical_tree` (bloom trigger after a
dry or cool spell plus a fixed cycle: coffee, cacao, mango, vanilla).

## Run
```bash
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
```
Offline demo (no internet, fake climate): choose "Synthetic" in the UI or add `source=synthetic`.

## API
```
GET /api/calendar?lat=-18.9&lon=47.5&source=nasa_power&irrigated=false
GET /api/calendar.csv?...          same parameters, CSV
GET /api/crops                     parameter table
```
Optional: `elevation` (m, lapse-rate 6.5 C/km correction), `start_year`, `end_year`, `crops=maize,rice`,
`start_month=1..12`, `overrides={"maize":{"gdd":1700},"onion":{"dl_min":11}}`.

## Files
- `crops.py`   crop parameter table (indicative values, edit/calibrate)
- `climate.py` NASA POWER / Open-Meteo fetchers, cache, daily climatology, ET0, day length
- `engine.py`  simulation: annual crops (sowing-date scan) and perennials (chilling, budbreak, GDD)
- `app.py`     Flask routes; `index.html` UI

## Method (short)
1. 30-year daily climatology (mean Tmax/Tmin/rain, P10 of Tmin as frost proxy, P90 of Tmax as heat proxy).
2. For each sowing day: GDD to maturity, frost kill, temperature trapezoid, heat stress at sensitive stage,
   photoperiod, rainfed water ratio (FAO-33 linear Ky), seedbed moisture, dry-harvest penalty.
3. Windows: recommended >= 85 % of best score, acceptable >= 65 %; harvest window from recommended dates.

## Limits
- Result is feasibility, not observed practice. Parameters are indicative and must be calibrated.
- Climatology means smooth out dry spells; for production use year-by-year simulation with an FAO-56 soil water balance.
- Reanalysis rainfall is uncertain in the tropics (consider CHIRPS). Cultivar differences are large (onion, soybean, cassava).

## References (verify details before citing)
- Allen et al. (1998) FAO Irrigation & Drainage Paper 56.
- Doorenbos & Kassam (1979) FAO Paper 33.
- Hargreaves & Samani (1985) Appl. Eng. Agric. 1(2).
- McMaster & Wilhelm (1997) Agric. For. Meteorol. 87.
- Ramirez-Villegas et al. (2013) Agric. For. Meteorol. 170 (EcoCrop).
- Sacks et al. (2010) Global Ecol. Biogeogr. 19; Portmann et al. (2010) Global Biogeochem. Cycles 24; Jägermeyr & Frieler (2018) Sci. Adv. 4.
- Hersbach et al. (2020) QJRMS 146; Funk et al. (2015) Sci. Data 2 (CHIRPS).
