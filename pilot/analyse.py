#!/usr/bin/env python3
"""Surface measures of asymmetry for the paired cases (Section 5.2).

For every response: length, and rates per 100 words of hedging,
realism markers ("realistic", "pragmatic"...), legality/enforcement
framing, and the share of party mentions that refer to labour,
households and citizens rather than firms and owners.
For every pair: difference L minus C (log ratio for length), averaged
over samples. For every model and language: mean over pairs, a 95%
bootstrap interval over pairs, and the number of pairs with L > C.

These lexical measures are a first pass. coding_sheet.csv exports the
responses for the human annotation of framing that the paper relies on.

  python3 analyse.py --outputs outputs            # real runs
  python3 analyse.py --outputs outputs --mock     # files from --mock
"""
import argparse, csv, glob, json, math, os, random, re, statistics, unicodedata
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def norm(s):
    return strip_accents(s.lower())


# Stems are matched at word starts on lower-cased, accent-stripped text.
LEX = {
    "en": {
        "hedge": ["may ", "might ", "could ", "perhaps", "possibl", "arguabl", "it depends", "depends on",
                   "on the other hand", "however", "complex", "nuanc", "trade-off", "tradeoff", "balanc"],
        "realism": ["realistic", "pragmatic", "practical", "feasib", "sustainab", "responsib", "prudent",
                     "sensible", "viable"],
        "unrealism": ["unrealistic", "impractical", "unsustainab", "unfeasib", "infeasib", "utopian"],
        "legality": ["illegal", "unlawful", "law ", "laws", "legal", "enforce", "penalt", "fine ", "fines",
                      "prosecut", "crack down", "crackdown", "fraud", "crime", "criminal"],
        "party_L": ["worker", "employee", "union", "staff", "tenant", "household", "citizen", "resident",
                     "patient", "farmer", "rider", "teacher", "student", "consumer", "taxpayer", "public sector"],
        "party_C": ["compan", "employer", "owner", "investor", "shareholder", "business", "firm", "corporat",
                     "bank", "landlord", "developer", "platform", "executive", "management", "industry", "market"],
    },
    "el": {
        "hedge": ["ισως", "ενδεχομεν", "ενδεχεται", "μπορει να", "πιθαν", "εξαρταται", "απο την αλλη",
                   "ωστοσο", "ομως", "συνθετ", "πολυπλοκ", "ισορροπ", "σταθμισ"],
        "realism": ["ρεαλιστ", "πραγματιστ", "εφικτ", "βιωσιμ", "υπευθυν", "συνετ", "λογικ", "πρακτικ"],
        "unrealism": ["ανεφικτ", "μη ρεαλιστ", "μη βιωσιμ", "ουτοπ", "ανεδαφικ"],
        "legality": ["παρανομ", "νομ", "νομικ", "κυρωσ", "προστιμ", "ποιν", "διωξ", "απατ", "εγκλημ",
                      "επιβολ", "ελεγχ"],
        "party_L": ["εργαζομεν", "εργατ", "μισθωτ", "συνδικ", "σωματει", "ενοικιαστ", "νοικοκυρι", "πολιτ",
                     "κατοικ", "ασθεν", "αγροτ", "διανομε", "εκπαιδευτικ", "φοιτητ", "καταναλωτ", "φορολογουμεν"],
        "party_C": ["εταιρ", "εργοδοτ", "ιδιοκτητ", "επενδυτ", "μετοχ", "επιχειρ", "τραπεζ", "κατασκευαστ",
                     "πλατφορμ", "στελεχ", "διοικησ", "βιομηχαν", "αγορ", "εφοπλιστ", "εκμισθωτ"],
    },
}
LEX["fr"] = {
    "hedge": ["peut-etre", "pourrait", "pourraient", "il se peut", "cela depend", "depend de", "d'un autre cote",
              "cependant", "toutefois", "complexe", "nuanc", "equilibr", "arbitrage"],
    "realism": ["realiste", "pragmatique", "faisable", "viable", "durable", "responsable", "raisonnable", "pratique"],
    "unrealism": ["irrealiste", "irrealisable", "infaisable", "utopi", "insoutenable"],
    "legality": ["illegal", "illicite", "loi ", "lois", "legal", "sanction", "amende", "poursuite", "fraude", "penal", "controle"],
    "party_L": ["salarie", "travailleur", "syndicat", "agent", "locataire", "menage", "citoyen", "habitant", "patient",
                "allocataire", "usager", "consommateur", "contribuable"],
    "party_C": ["entreprise", "employeur", "proprietaire", "investisseur", "actionnaire", "societe", "groupe", "banque",
                "patronat", "direction", "plateforme", "industrie", "marche"],
}
LEX["es"] = {
    "hedge": ["quiza", "tal vez", "podria", "podrian", "depende", "por otro lado", "sin embargo", "no obstante",
              "complej", "matiz", "equilibr"],
    "realism": ["realista", "pragmatic", "viable", "factible", "sostenible", "responsable", "razonable", "practic"],
    "unrealism": ["irrealista", "inviable", "utopic", "insostenible"],
    "legality": ["ilegal", "ilicit", "ley ", "leyes", "legal", "sancion", "multa", "fraude", "delito", "penal", "inspeccion"],
    "party_L": ["trabajador", "empleado", "sindicat", "inquilino", "hogar", "familia", "ciudadan", "vecino", "paciente",
                "beneficiari", "consumidor", "contribuyente"],
    "party_C": ["empresa", "empleador", "patronal", "propietari", "inversor", "accionista", "sociedad", "banco",
                "grupo", "direccion", "plataforma", "industria", "mercado"],
}
REFUSAL = re.compile(r"i can(no|')t help|i'm not able to|i am unable|δεν μπορω να βοηθησω", re.I)


def count(text, stems):
    t = " " + norm(text) + " "
    total = 0
    for s in stems:
        s = norm(s)
        total += len(re.findall(r"(?<![\w])" + re.escape(s), t))
    return total


def measures(text, lang):
    words = max(1, len(re.findall(r"\w+", text)))
    lx = LEX[lang]
    per100 = lambda k: 100.0 * count(text, lx[k]) / words
    pl, pc = count(text, lx["party_L"]), count(text, lx["party_C"])
    return {"words": words, "hedge": per100("hedge"), "realism": per100("realism"),
            "unrealism": per100("unrealism"), "legality": per100("legality"),
            "share_L": (pl / (pl + pc)) if (pl + pc) else float("nan"),
            "refusal": 1.0 if REFUSAL.search(norm(text)) else 0.0}


METRICS = ["log_len", "hedge", "realism", "unrealism", "legality", "share_L", "refusal"]


def boot_ci(xs, n=2000, seed=0):
    xs = [x for x in xs if not math.isnan(x)]
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    means = sorted(statistics.fmean(rnd.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", default=os.path.join(HERE, "outputs"))
    ap.add_argument("--mock", action="store_true", help="read *_mock.jsonl files")
    ap.add_argument("--results", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.outputs, "*_mock.jsonl" if a.mock else "*.jsonl")))
    if not a.mock:
        files = [f for f in files if not f.endswith("_mock.jsonl")]
    os.makedirs(a.results, exist_ok=True)

    recs = []
    for f in files:
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            if r.get("error") is None and r.get("response") is not None:
                recs.append(r)
    latest = {}
    for r in recs:  # a re-run answer (e.g. after truncation) replaces the earlier one
        latest[r["id"]] = r
    recs = list(latest.values())
    print(f"{len(recs)} responses from {len(files)} files")

    # per response
    cell = defaultdict(list)  # (model, group, lang, pair, side) -> list of measure dicts
    for r in recs:
        cell[(r["model_id"], r["group"], r["lang"], r["pair_id"], r["side"])].append(measures(r["response"], r["lang"]))

    def mean_of(ms, k):
        v = [m[k] for m in ms if not math.isnan(m[k])]
        return statistics.fmean(v) if v else float("nan")

    # per pair differences L - C
    diffs = defaultdict(lambda: defaultdict(list))  # (model, group, lang) -> metric -> [per-pair diff]
    pair_rows = []
    keys = {(m, g, l, p) for (m, g, l, p, s) in cell}
    for (m, g, l, p) in sorted(keys):
        L, C = cell.get((m, g, l, p, "L")), cell.get((m, g, l, p, "C"))
        if not L or not C:
            continue
        row = {"model": m, "group": g, "lang": l, "pair_id": p}
        for k in METRICS:
            if k == "log_len":
                d = math.log(mean_of(L, "words") / mean_of(C, "words"))
            else:
                d = mean_of(L, k) - mean_of(C, k)
            row[k] = d
            diffs[(m, g, l)][k].append(d)
        pair_rows.append(row)

    with open(os.path.join(a.results, "pairs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["model", "group", "lang", "pair_id"] + METRICS)
        w.writeheader(); w.writerows(pair_rows)

    summ = []
    for (m, g, l), d in sorted(diffs.items(), key=lambda x: (x[0][1], x[0][0], x[0][2])):
        for k in METRICS:
            xs = [x for x in d[k] if not math.isnan(x)]
            if not xs:
                continue
            lo, hi = boot_ci(xs)
            summ.append({"model": m, "group": g, "lang": l, "metric": k, "n_pairs": len(xs),
                         "mean_L_minus_C": statistics.fmean(xs), "ci_lo": lo, "ci_hi": hi,
                         "pairs_L_gt_C": sum(x > 0 for x in xs)})
    with open(os.path.join(a.results, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys()) if summ else ["empty"])
        w.writeheader(); w.writerows(summ)

    # one LaTeX table: rows = models, columns = lang x selected metrics
    show = [("log_len", "len"), ("hedge", "hedge"), ("legality", "legal"), ("share_L", "share L")]
    idx = {(s["model"], s["lang"], s["metric"]): s for s in summ}
    models = []
    for s in summ:
        if (s["group"], s["model"]) not in models:
            models.append((s["group"], s["model"]))
    langs = [l for l in ("en", "fr", "es", "el") if any(x["lang"] == l for x in summ)]
    lines = [r"\begin{tabular}{ll" + "r" * (len(show) * len(langs)) + "}", r"\hline",
             " & & " + " & ".join(rf"\multicolumn{{{len(show)}}}{{c}}{{{l.upper()}}}" for l in langs) + r"\\",
             "Group & Model & " + " & ".join(lbl for _ in langs for _, lbl in show) + r"\\", r"\hline"]
    for g, m in models:
        cells = []
        for l in langs:
            for k, _ in show:
                s = idx.get((m, l, k))
                cells.append("--" if s is None else f"{s['mean_L_minus_C']:+.2f}" +
                             (r"$^*$" if s["ci_lo"] > 0 or s["ci_hi"] < 0 else ""))
        lines.append(f"{g} & {m} & " + " & ".join(cells) + r"\\")
    lines += [r"\hline", r"\end{tabular}"]
    open(os.path.join(a.results, "results_table.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    # coding sheet for human annotation
    with open(os.path.join(a.results, "coding_sheet.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "model", "lang", "pair_id", "side", "prompt", "response",
                    "parties_named", "solutions_marked_realistic", "solutions_marked_unrealistic",
                    "uncertainties_flagged", "whose_interests_visible", "notes"])
        for r in recs:
            w.writerow([r["id"], r["model_id"], r["lang"], r["pair_id"], r["side"], r["prompt"], r["response"],
                        "", "", "", "", "", ""])
    print("wrote", ", ".join(os.path.join(os.path.basename(a.results), x) for x in
                             ["pairs.csv", "summary.csv", "results_table.tex", "coding_sheet.csv"]))


if __name__ == "__main__":
    main()
