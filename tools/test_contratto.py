# -*- coding: utf-8 -*-
"""Test del contratto v1.2: ogni file di una cartella pubblicata (manifest + file citati) contro schema/v1.2.json, piu'
i vincoli della sezione 9 di v1.2.md che lo schema non esprime, piu' mutazioni che lo schema DEVE rifiutare.

  python contratto/test_contratto.py [cartella ...]     (senza argomenti: contratto/esempi e contratto/esempi/demo)
Codice d'uscita 0 solo se tutto passa.
"""
import copy, hashlib, json, os, re, sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator
from shapely.geometry import Point, shape
from shapely.ops import unary_union

QUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA = json.load(open(os.path.join(os.path.dirname(QUI), "schema", "v1.2.json"), encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)
ROMA = ZoneInfo("Europe/Rome")
CASI = {"dull", "worth", "spectacular", "low_deck", "clear"}          # BY6: sea_of_clouds facoltativo
# sezione 12: criterio di ciascun demo_case su TUTTI i punti con previsione della serata (BX3)
SOGLIA_CASO = dict(spectacular=0.2, worth=0.5, dull=0.5, low_deck=0.3, clear=0.5, sea_of_clouds=0.2)


def criterio_caso(caso, punti, bande):
    V = list(punti.values()); n = float(len(V))
    fr = lambda cond: sum(1 for v in V if cond(v)) / n
    low, mid = bande["worth"][0]["max"], bande["worth"][1]["max"]
    spec = bande["spectacular"][0]["max"]
    sh = fr(lambda v: v["p_spectacular"] >= spec)
    return dict(spectacular=sh, worth=fr(lambda v: v["p_worth"] >= low and v["p_spectacular"] < spec),   # BY6
                dull=fr(lambda v: v["p_worth"] < low),
                low_deck=fr(lambda v: v["limiting_factors"][:1] == ["low_deck_overhead"]),
                clear=fr(lambda v: v["canvas"] == "clear"),
                sea_of_clouds=fr(lambda v: "possible_sea_of_clouds" in v["flags"]))[caso]
errori = []


def validatore(nome):
    s = dict(SCHEMA)
    s["$ref"] = "#/$defs/%s" % nome
    return Draft202012Validator(s)


V = {n: validatore(n) for n in ("manifest", "points", "forecast", "potential", "coverage")}


def ko(msg):
    errori.append(msg)
    print("  FALLITO:", msg)


def schema(nome, obj, file):
    e = sorted(V[nome].iter_errors(obj), key=lambda x: list(x.path))
    for x in e[:5]:
        ko("%s: schema %s: %s" % (file, "/".join(map(str, x.path)), x.message[:160]))
    return not e


def residuo(a, b):
    """area di a fuori da b (o di a dentro b, passando a.intersection) ammessa come residuo della griglia di 1e-5:
    al massimo il perimetro per mezzo passo (v1.2.md, sezione 9)"""
    return a.area <= max(b.length, 1e-12) * 0.5e-5


def valida(g, file):
    if not g.is_valid:
        from shapely.validation import explain_validity
        ko("%s: geometria non valida: %s" % (file, explain_validity(g)))
    return g


def cinque(c, file):
    if isinstance(c, list):
        for x in c:
            cinque(x, file)
    elif isinstance(c, (int, float)) and round(c, 5) != c:
        ko("%s: coordinata con piu' di 5 decimali: %r" % (file, c))


def orario(s, file, campo):
    t = datetime.fromisoformat(s)
    if t.utcoffset() != t.replace(tzinfo=ROMA).utcoffset():
        ko("%s: %s con offset diverso da Europe/Rome: %s" % (file, campo, s))
    return t


def carica(cartella, nome):
    p = os.path.join(cartella, nome)
    b = open(p, "rb").read()
    if nome != "manifest.json":
        h = re.search(r"_([0-9a-f]{6})\.(json|geojson)$", nome).group(1)
        if hashlib.sha256(b).hexdigest()[:6] != h:
            ko("%s: impronta nel nome diversa dal contenuto" % nome)
    return json.loads(b.decode("utf-8"))


def cartella(c):
    print("cartella", c)
    m = carica(c, "manifest.json")
    if not schema("manifest", m, "manifest.json"):
        return
    # fasce: crescenti, ultima null, observed_rate crescenti, 2 decimali
    for k, lista in m["bands"].items():
        mx = [b["max"] for b in lista]
        if mx[-1] is not None or any(x is None for x in mx[:-1]) or mx[:-1] != sorted(mx[:-1]) or len(set(mx[:-1])) != len(mx) - 1:
            ko("bands.%s: max non crescenti o ultima non null" % k)
        if len({b["id"] for b in lista}) != len(lista):
            ko("bands.%s: id ripetuti" % k)
        if True:
            for campo in ("observed_rate", "shown_rate"):
                r = [b[campo] for b in lista]
                if r != sorted(r) or any(round(x, 2) != x for x in r):
                    ko("bands.%s: %s non crescenti o non a 2 decimali" % (k, campo))
            for b in lista:
                if b["shown_rate_source"] == "calibration_sample" and b["shown_rate"] != b["observed_rate"]:
                    ko("bands.%s/%s: shown_rate diverso da observed_rate con fonte calibration_sample" % (k, b["id"]))
    orario(m["generated_at"], "manifest", "generated_at")
    soglia_low = m["bands"]["worth"][0]["max"]
    # copertura e punti
    cov = carica(c, m["coverage"]["file"])
    schema("coverage", cov, m["coverage"]["file"])
    zone = {f["properties"]["id"]: valida(shape(f["geometry"]), "coverage") for f in cov["features"] if f["properties"]["kind"] == "zone"}
    rec = [(f["properties"]["zone"], valida(shape(f["geometry"]), "coverage")) for f in cov["features"] if f["properties"]["kind"] == "fenced"]
    for z, g in rec:
        if z not in zone:
            ko("coverage: recinto di una zona inesistente %s" % z)
        elif not residuo(g.difference(zone[z]), g):
            ko("coverage: recinto fuori dalla sua zona %s" % z)
    recinto = unary_union([g for _, g in rec]) if rec else None
    if recinto is not None and residuo(recinto, recinto):
        ko("tolleranza vuota: il recinto intero passa come residuo")
    for f in cov["features"]:
        cinque(f["geometry"]["coordinates"], "coverage")
        if f["properties"]["kind"] == "zone":
            cinque(f["properties"]["reference_point"], "coverage")
    pts = carica(c, m["points"]["file"])
    schema("points", pts, m["points"]["file"])
    ids = set()
    for f in pts["features"]:
        p = f["properties"]
        cinque(f["geometry"]["coordinates"], "points")
        if p["id"] in ids:
            ko("points: id ripetuto %s" % p["id"])
        ids.add(p["id"])
        dip = -1.76 * max(p["elevation_m"], 0) ** 0.5 / 60.0
        if min(p["horizon"]["elevation_deg"]) < dip - 0.02:
            ko("points: %s orizzonte sotto il dip (%.2f < %.2f)" % (p["id"], min(p["horizon"]["elevation_deg"]), dip))
        if p["zone"] not in zone:
            ko("points: %s in zona inesistente %s" % (p["id"], p["zone"]))
        elif not zone[p["zone"]].buffer(2e-5).contains(Point(f["geometry"]["coordinates"])):
            ko("points: %s fuori dalla sua zona %s" % (p["id"], p["zone"]))
    ids_rec = {f["properties"]["id"] for f in pts["features"]
               if recinto is not None and recinto.contains(Point(f["geometry"]["coordinates"]))}
    # serate (BX3: modelli, anticipo e affidabilita' per zona)
    zp = {f["properties"]["id"]: f["properties"] for f in cov["features"] if f["properties"]["kind"] == "zone"}
    stagione = (m.get("validated_season") or {}).get("months")
    casi, non_cal = set(), 0
    for e in m["evenings"]:
        if set(e["weather_models"]) != set(zp):
            ko("%s: weather_models con zone diverse da coverage" % e["date"])
        for z, w in e["weather_models"].items():
            nomi = [x["name"] for x in w["models"]]
            if len(set(nomi)) != len(nomi) or "ICON-D2" not in nomi:
                ko("%s/%s: modelli ripetuti o senza ICON-D2" % (e["date"], z))
            if "ICON-EU" in nomi and zp.get(z, {}).get("weather_model") != "ICON-D2+ICON-EU":
                ko("%s/%s: ICON-EU in una zona solo ICON-D2" % (e["date"], z))
            rel = w["lead_reliability"]
            if rel == "calibrated" and w["lead_time_h"] > m["engine"]["calibrated_lead_h_max"]:
                ko("%s/%s: calibrated con lead_time_h %d" % (e["date"], z, w["lead_time_h"]))
            if zp.get(z, {}).get("calibration") == "indicative" and rel != "unmeasured":
                ko("%s/%s: zona indicative non unmeasured" % (e["date"], z))
            if rel in ("measured_close", "measured_degraded") and not stagione:
                ko("%s/%s: %s senza validated_season" % (e["date"], z, rel))
            if rel == "measured_close" and stagione and int(e["date"][5:7]) not in stagione:
                ko("%s/%s: measured_close fuori dalla stagione validata" % (e["date"], z))
        alps = [w for z, w in e["weather_models"].items() if zp.get(z, {}).get("calibration") == "alps"]
        if any(w["lead_reliability"] != "calibrated" for w in alps):
            non_cal += 1
        casi.add(e.get("demo_case"))
        if not e["forecast"].startswith("forecast_%s_" % e["date"]) or not e["potential"].startswith("potential_%s_" % e["date"]):
            ko("%s: data nel nome dei file diversa da quella della serata" % e["date"])
        fc = carica(c, e["forecast"])
        if not schema("forecast", fc, e["forecast"]):
            continue
        if fc["date"] != e["date"]:
            ko("%s: date diversa nel file di previsione" % e["forecast"])
        if m["demo"] and fc["points"]:
            v = criterio_caso(e["demo_case"], fc["points"], m["bands"])
            if v < SOGLIA_CASO[e["demo_case"]]:
                ko("%s: demo_case %s non soddisfa il suo criterio (%.2f < %.2f)" % (e["date"], e["demo_case"], v,
                                                                                    SOGLIA_CASO[e["demo_case"]]))
        for pid, q in fc["points"].items():
            dove = "%s %s" % (e["forecast"], pid)
            if pid not in ids:
                ko("%s: punto assente da points" % dove)
            if pid in ids_rec:
                ko("%s: punto dentro il recinto con previsione" % dove)
            for k in ("p_worth", "p_spectacular"):
                if round(q[k], 2) != q[k]:
                    ko("%s: %s non a 2 decimali" % (dove, k))
            if q["p_spectacular"] > q["p_worth"]:
                ko("%s: p_spectacular > p_worth" % dove)
            if bool(q["limiting_factors"]) != (q["p_worth"] < soglia_low):
                ko("%s: limiting_factors non vuoto se e solo se p_worth < %s" % (dove, soglia_low))
            sf = orario(q["sunset_flat_horizon"], dove, "sunset_flat_horizon")
            if sf.date().isoformat() != e["date"]:
                ko("%s: tramonto in un'altra data" % dove)
            if "sun_hidden_at" in q:
                orario(q["sun_hidden_at"], dove, "sun_hidden_at")
            if "best_time" in q:
                b, w = orario(q["best_time"], dove, "best_time"), q["best_window"]
                if not orario(w["start"], dove, "start") <= b <= orario(w["end"], dove, "end"):
                    ko("%s: best_time fuori da best_window" % dove)
        pot = carica(c, e["potential"])
        if schema("potential", pot, e["potential"]):
            bande = {b["id"]: b for b in m["bands"]["worth"]}                # BX3: potenziale nelle fasce di worth
            gs = []
            for f in pot["features"]:
                cinque(f["geometry"]["coordinates"], e["potential"])
                pr = f["properties"]
                if not pr["value_min"] <= pr["value_max"] or pr["band"] not in bande:
                    ko("%s: banda o valori incoerenti" % e["potential"])
                g = valida(shape(f["geometry"]), e["potential"])
                if not g.is_valid:
                    continue
                if recinto is not None and not residuo(g.intersection(recinto), g):
                    ko("%s: potenziale dentro il recinto" % e["potential"])
                if not residuo(g.difference(unary_union(list(zone.values()))), g):
                    ko("%s: potenziale fuori dalle zone" % e["potential"])
                gs.append(g)
            for i in range(len(gs)):
                for j in range(i + 1, len(gs)):
                    if not residuo(gs[i].intersection(gs[j]), gs[i]):
                        ko("%s: poligoni sovrapposti" % e["potential"])
    if m["demo"]:
        if not CASI <= casi:
            ko("demo: mancano i casi %s" % sorted(CASI - casi))
        if non_cal == 0:
            ko("demo: manca una serata non calibrated")
    print("  serate %d, punti %d (recintati %d), errori finora %d" % (len(m["evenings"]), len(ids), len(ids_rec), len(errori)))
    return m, fc


def mutazioni(m, fc):
    """lo schema DEVE rifiutare ciascuna di queste"""
    pid = next(iter(fc["points"]))
    casi = []

    def mm(f):
        x = copy.deepcopy(m); f(x); return x

    def ff(f):
        x = copy.deepcopy(fc); f(x); return x
    casi += [
        ("manifest", mm(lambda x: x.__setitem__("schema_version", "1.1")), "versione 1.1"),
        ("manifest", mm(lambda x: x["engine"].__setitem__("best_time_bias_corrected", True)), "bias corretto true"),
        ("manifest", mm(lambda x: [w.__setitem__("within_calibrated_lead", w["lead_reliability"] != "calibrated")
                                   for w in x["evenings"][0]["weather_models"].values()]),
         "within_calibrated_lead incoerente"),
        ("manifest", mm(lambda x: x["evenings"][0].__setitem__("demo_case", "dull") if not x["demo"] else x["evenings"][0].pop("demo_case")),
         "demo_case fuori posto"),
        ("manifest", mm(lambda x: x["attribution"][0].__setitem__("scope", "footer")), "scope sconosciuto"),
        ("manifest", mm(lambda x: next(iter(x["evenings"][0]["weather_models"].values()))["models"][0].__setitem__(
            "run", "2026-10-15T06:00:00+02:00")), "run non UTC"),
        ("manifest", mm(lambda x: x["bands"].__setitem__("potential", [{"id": "zero", "max": None}])), "bands.potential (tolto)"),
        ("manifest", mm(lambda x: x.pop("validated_season")), "validated_season mancante"),
        ("forecast", ff(lambda x: x["points"][pid].__setitem__("visible_canvas_km", {"near": 5, "far": 86})), "visible_canvas_km presente"),
        ("forecast", ff(lambda x: x["points"][pid].__setitem__("canvas", "cirrus")), "canvas cirrus (v1.1)"),
        ("forecast", ff(lambda x: x["points"][pid].__setitem__("sunset_flat_horizon", "2026-10-15T18:24:31+02:00")), "secondi non nulli"),
        ("forecast", ff(lambda x: x["points"][pid].pop("sun_hidden_at", None) or x["points"][pid].__setitem__("flags", [])),
         "sun_hidden_at assente senza flag"),
        ("forecast", ff(lambda x: x["points"].__setitem__("node/1", x["points"][pid])), "id senza prefisso osm:"),
    ]
    con_bt = next((k for k, q in fc["points"].items() if "best_time" in q), None)
    if con_bt:
        casi.append(("forecast", ff(lambda x: x["points"][con_bt].pop("best_window")), "best_window mancante con tela"))
    senza = next((k for k, q in fc["points"].items() if q["canvas"] == "none"), None)
    if senza:
        casi.append(("forecast", ff(lambda x: x["points"][senza].__setitem__("visible_canvas_max_km", 80)),
                     "visible_canvas_max_km senza tela da nube"))
        casi.append(("manifest", mm(lambda x: x["bands"]["worth"][0].pop("shown_rate_source")), "shown_rate_source mancante"))
    if senza:
        casi.append(("forecast", ff(lambda x: x["points"][senza].__setitem__("best_time", "2026-10-15T18:00:00+02:00")),
                     "best_time con tela none"))
    mare = next((k for k, q in fc["points"].items() if "possible_sea_of_clouds" in q["flags"]), None)
    if mare:
        casi.append(("forecast", ff(lambda x: x["points"][mare].__setitem__("limiting_factors", ["low_deck_overhead"])),
                     "low_deck_overhead col flag del mare"))
    for nome, obj, desc in casi:
        if V[nome].is_valid(obj):
            ko("mutazione ACCETTATA dallo schema: %s" % desc)
    print("mutazioni rifiutate %d su %d" % (sum(not V[n].is_valid(o) for n, o, _ in casi), len(casi)))


if __name__ == "__main__":
    cc = sys.argv[1:] or [os.path.join(os.path.dirname(QUI), "examples")]
    ultimo = None
    for c in cc:
        r = cartella(c)
        ultimo = ultimo or r
    if ultimo:
        mutazioni(*ultimo)
    print("ESITO:", "TUTTO OK" if not errori else "%d ERRORI" % len(errori))
    sys.exit(0 if not errori else 1)
