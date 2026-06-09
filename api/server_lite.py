"""
API Flask — arbitrages sportifs via The Odds API (gratuit, 500 req/mois)
Inscription gratuite sur https://the-odds-api.com pour obtenir une clé API.
Lancez avec : python api/server_lite.py
"""
import os, json, threading, datetime, time, pathlib
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,OPTIONS'
    response.headers['CF-Access-Allow-Authd-Requests'] = 'false'
    return response

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
ODDS_API_KEY  = os.environ.get("ODDS_API_KEY", "2dd8f5e82d2c99c2950e7c9aae554d22")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Seuil minimum pour afficher une opportunité :
#   = 1.0  → uniquement les vrais arbitrages (TRJ > 100%)
#   < 1.0  → inclut les near-arbs, ex. 0.985 = TRJ > 98.5%
# ⚠ Mettre trop bas flood l'affichage — 0.985 est un bon compromis
MIN_TRJ_RATIO = 0.985

# Refresh toutes les N secondes (300 = 5 min, 600 = 10 min)
# Avec 500 req/mois et ~20 sports actifs max : 600s = ~700 req/mois (léger dépassement)
# Pour rester safe : 900s = 3 scan/h × 24h × 30j × 20 req ≈ trop élevé
# Formule : 500 req / (N_sports × 30j × 24h × 3600 / REFRESH_SEC) ≈ budget
# Avec ~15 sports actifs : 500 / (15 × 30) ≈ 1 scan/jour → trop peu
# Solution : on ne scanne que les sports qui ont des matchs (via /sports actifs)
REFRESH_SEC = 600  # 10 minutes

# Candidats sports à scanner — on filtrera dynamiquement ceux avec des matchs actifs
# Classés par priorité (bookmakers divergent plus sur les marchés moins surveillés)
SPORT_CANDIDATES = [
    # Football — grands championnats + ligues secondaires
    ("football", "soccer_fifa_world_cup"),
    ("football", "soccer_uefa_nations_league_a"),
    ("football", "soccer_uefa_nations_league"),
    ("football", "soccer_conmebol_copa_america"),
    ("football", "soccer_france_ligue1"),
    ("football", "soccer_france_ligue2"),          # ← Ligue 2
    ("football", "soccer_epl"),
    ("football", "soccer_england_league1"),        # ← League One
    ("football", "soccer_england_league2"),        # ← League Two
    ("football", "soccer_spain_la_liga"),
    ("football", "soccer_spain_segunda_division"),
    ("football", "soccer_germany_bundesliga"),
    ("football", "soccer_germany_bundesliga2"),
    ("football", "soccer_italy_serie_a"),
    ("football", "soccer_italy_serie_b"),
    ("football", "soccer_brazil_campeonato"),      # ← Brasileirão
    ("football", "soccer_argentina_primera_division"),
    ("football", "soccer_mexico_ligamx"),
    ("football", "soccer_netherlands_eredivisie"),
    ("football", "soccer_portugal_primeira_liga"),
    ("football", "soccer_turkey_super_league"),
    ("football", "soccer_uefa_champs_league"),
    ("football", "soccer_uefa_europa_league"),
    ("football", "soccer_usa_mls"),
    # Basketball
    ("basketball", "basketball_nba"),
    ("basketball", "basketball_ncaab"),
    ("basketball", "basketball_euroleague"),
    ("basketball", "basketball_nbl"),              # ← Australie
    # Tennis (les bookmakers divergent beaucoup sur les tournois mineurs)
    ("tennis", "tennis_atp_french_open"),
    ("tennis", "tennis_wta_french_open"),
    ("tennis", "tennis_atp_wimbledon"),
    ("tennis", "tennis_wta_wimbledon"),
    ("tennis", "tennis_atp_us_open"),
    ("tennis", "tennis_wta_us_open"),
    ("tennis", "tennis_atp_aus_open"),
    ("tennis", "tennis_wta_aus_open"),
    # MMA/UFC — écarts de cotes souvent importants entre bookmakers
    ("mma", "mma_mixed_martial_arts"),
    # Rugby
    ("rugby", "rugbyleague_nrl"),
    ("rugby", "rugbyunion_premiership"),
    ("rugby", "rugbyunion_six_nations"),
    # Baseball
    ("baseball", "baseball_mlb"),
    # Hockey
    ("hockey", "icehockey_nhl"),
]

CACHE = {
    "arbitrages": [], "freebets": [], "kpis": {},
    "last_update": None, "status": "initializing",
    "api_key_configured": False, "requests_remaining": "?",
    "active_sports": 0, "total_matches_scanned": 0,
}
LOCK = threading.Lock()

HISTORY_FILE = pathlib.Path(__file__).parent / "history.json"
MAX_HISTORY   = 2000


def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(entries):
    try:
        HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  Erreur sauvegarde historique: {e}")


def append_to_history(arbs, snapshot_time):
    history = load_history()
    existing_keys = {(e["match"], e["bookmakers"]) for e in history}
    added = 0
    for arb in arbs:
        if arb.get("status") == "near_arb":
            continue  # On n'historise que les vrais arbitrages
        key = (arb["match"], arb["bookmakers"])
        if key not in existing_keys:
            entry = dict(arb)
            entry["detected_at"] = snapshot_time
            history.append(entry)
            existing_keys.add(key)
            added += 1
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    save_history(history)
    return added


def get_active_sport_keys():
    """
    Interroge /sports pour obtenir uniquement les compétitions
    qui ont des matchs à venir — évite de gaspiller des requêtes.
    Coûte 1 requête, en économise potentiellement 20+.
    """
    url = f"{ODDS_API_BASE}/sports/"
    try:
        r = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=10)
        if r.status_code != 200:
            return None  # En cas d'erreur, on scanne tout
        active = {s["key"] for s in r.json() if s.get("active") and not s.get("has_outrights")}
        return active
    except Exception:
        return None


def check_api_key():
    """Vérifie que la clé API est valide via /sports (coût : 0 requête de quota)."""
    url = f"{ODDS_API_BASE}/sports/"
    try:
        r = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def fetch_odds(sport_key):
    """Récupère les cotes depuis The Odds API pour un sport donné."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk,us,au",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        remaining = r.headers.get("x-requests-remaining", "?")
        if r.status_code == 200:
            data = r.json()
            return (data if isinstance(data, list) else []), remaining
        if r.status_code == 401:
            # Certains sports nécessitent un plan payant → on passe au suivant
            print(f"    → {sport_key} non disponible sur ce plan (401), ignoré")
            return [], remaining
        if r.status_code == 422:
            # Sport inexistant ou hors saison
            return [], remaining
        if r.status_code == 429:
            print("  Quota API épuisé pour ce mois.")
            return None, "quota"
        print(f"    → Erreur HTTP {r.status_code} pour {sport_key}")
        return [], remaining
    except Exception as e:
        print(f"  Erreur réseau {sport_key}: {e}")
        return [], "error"


def parse_matches(events, sport_name):
    matches = []
    for ev in events:
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        odds_by_book = {}
        for bm in ev.get("bookmakers", []):
            key = bm.get("key", "")
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                if outcomes:
                    odds_by_book[key] = {o["name"]: o["price"] for o in outcomes}
        if len(odds_by_book) >= 2:
            matches.append({
                "match": f"{home} vs {away}",
                "sport": sport_name,
                "date": ev.get("commence_time", ""),
                "odds_full": odds_by_book,
            })
    return matches


def find_arbitrages(matches, min_ratio=MIN_TRJ_RATIO):
    """
    Détecte les arbitrages et near-arbs.
    min_ratio < 1.0 : inclut les opportunités proches (value betting).
    Un vrai arbitrage a trj_inv < 1.0 (gain garanti).
    Un near-arb a 1.0 <= trj_inv < (1/min_ratio), ex. < 1.015 pour 98.5%.
    """
    results = []
    for m in matches:
        odds_full = m["odds_full"]
        if len(odds_full) < 2:
            continue

        all_teams = set()
        for bm_odds in odds_full.values():
            all_teams.update(bm_odds.keys())
        all_teams = list(all_teams)

        if len(all_teams) not in (2, 3):
            continue

        best_per_outcome = {}
        for team in all_teams:
            best_odd, best_bm = 0, ""
            for bm, bm_odds in odds_full.items():
                if team in bm_odds and bm_odds[team] > best_odd:
                    best_odd = bm_odds[team]
                    best_bm = bm
            if best_odd > 0:
                best_per_outcome[team] = (best_bm, best_odd)

        if len(best_per_outcome) < len(all_teams):
            continue

        trj_inv = sum(1 / v[1] for v in best_per_outcome.values())

        # Filtre : on garde seulement si trj_inv < 1/min_ratio
        if trj_inv >= (1 / min_ratio):
            continue

        is_arb    = trj_inv < 1.0
        trj       = round(100 / trj_inv, 3)
        gain_100  = round((1 / trj_inv - 1) * 100, 2)
        bms_used  = set(v[0] for v in best_per_outcome.values())

        breakdown = []
        for team, (bm, odd) in best_per_outcome.items():
            breakdown.append({
                "outcome":    team,
                "bookmaker":  bm,
                "odd":        odd,
                "stake_pct":  round((1 / odd) / trj_inv * 100, 2),
            })

        results.append({
            "match":       m["match"],
            "sport":       m["sport"],
            "competition": "",
            "bookmakers":  " / ".join(bms_used),
            "cotes":       " / ".join(str(v[1]) for v in best_per_outcome.values()),
            "trj":         trj,
            "gain_100":    gain_100,
            "date":        m.get("date", ""),
            # "arb" = gain garanti, "near_arb" = value / presque arb
            "status":      "arb" if is_arb else "near_arb",
            "breakdown":   breakdown,
        })

    results.sort(key=lambda x: x["trj"], reverse=True)
    return results[:30]  # Top 30 au lieu de 20


def refresh_loop():
    while True:
        if not ODDS_API_KEY:
            with LOCK:
                CACHE["status"] = "no_api_key"
                CACHE["api_key_configured"] = False
            print("  CONFIGURATION REQUISE — ajoutez votre clé ODDS_API_KEY dans server_lite.py")
            time.sleep(30)
            continue

        try:
            with LOCK:
                CACHE["status"] = "refreshing"
                CACHE["api_key_configured"] = True

            # Étape 1 : validation de la clé via /sports (gratuit, hors quota)
            print("  Vérification de la clé API...")
            if not check_api_key():
                print("  ERREUR FATALE: Clé API invalide. Vérifiez ODDS_API_KEY dans server_lite.py")
                with LOCK:
                    CACHE["status"] = "invalid_key"
                time.sleep(60)
                continue

            # Étape 2 : quels sports ont des matchs actifs ?
            print("  Récupération des sports actifs...")
            active_keys = get_active_sport_keys()
            if active_keys is not None:
                print(f"  → {len(active_keys)} sports actifs détectés")
            else:
                print("  → Scan complet (filtre indisponible)")

            # Étape 3 : scan des sports actifs de notre liste
            all_matches = []
            remaining   = "?"
            stop        = False
            scanned     = 0

            for sport_name, sport_key in SPORT_CANDIDATES:
                if stop:
                    break
                if active_keys is not None and sport_key not in active_keys:
                    continue

                print(f"  Scan {sport_key}...")
                events, rem = fetch_odds(sport_key)

                if events is None:
                    if rem == "quota":
                        print("  Quota mensuel épuisé.")
                        with LOCK:
                            CACHE["status"] = "quota_exhausted"
                        stop = True
                        break
                    continue

                if rem not in ("?", "error"):
                    remaining = rem
                scanned  += 1
                matches   = parse_matches(events, sport_name)
                if matches:
                    all_matches.extend(matches)
                    print(f"    → {len(matches)} matchs")
                time.sleep(1)

            arbs     = find_arbitrages(all_matches)
            real_arbs = [a for a in arbs if a["status"] == "arb"]
            nb_arb    = len(real_arbs)
            nb_near   = len(arbs) - nb_arb
            avg_trj   = round(sum(a["trj"] for a in real_arbs) / nb_arb, 3) if nb_arb else 100.0
            gain_total = round(sum(a["gain_100"] for a in real_arbs), 2)

            with LOCK:
                CACHE["arbitrages"]            = arbs
                CACHE["freebets"]              = []
                CACHE["kpis"]                  = {
                    "nb_arbitrages":  nb_arb,
                    "nb_near_arbs":   nb_near,
                    "gain_potentiel": gain_total,
                    "trj_moyen":      avg_trj,
                    "nb_bookmakers":  len(set(
                        b for a in real_arbs for b in a["bookmakers"].split(" / ")
                    )) if real_arbs else 0,
                    "nb_freebets":    0,
                }
                CACHE["last_update"]           = datetime.datetime.now().isoformat()
                CACHE["status"]                = "ok"
                CACHE["requests_remaining"]    = remaining
                CACHE["active_sports"]         = scanned
                CACHE["total_matches_scanned"] = len(all_matches)

            snapshot_time = datetime.datetime.now().isoformat()
            added = append_to_history(real_arbs, snapshot_time)
            ts    = datetime.datetime.now().strftime("%H:%M:%S")
            print(
                f"[{ts}] Rafraîchi — {nb_arb} arbs | {nb_near} near-arbs | "
                f"{len(all_matches)} matchs | {scanned} sports | "
                f"+{added} historique | Quota restant: {remaining}"
            )

        except Exception as e:
            with LOCK:
                CACHE["status"] = f"error: {e}"
            print(f"Erreur: {e}")
            import traceback; traceback.print_exc()

        time.sleep(REFRESH_SEC)


@app.route("/api/status")
def status():
    with LOCK:
        return jsonify({
            "status":              CACHE["status"],
            "last_update":         CACHE["last_update"],
            "api_key_configured":  CACHE["api_key_configured"],
            "requests_remaining":  CACHE["requests_remaining"],
            "active_sports":       CACHE["active_sports"],
            "total_matches":       CACHE["total_matches_scanned"],
        })

@app.route("/api/kpis")
def kpis():
    with LOCK:
        return jsonify(CACHE["kpis"])

@app.route("/api/arbitrages")
def arbitrages():
    with LOCK:
        return jsonify(CACHE["arbitrages"])

@app.route("/api/freebets")
def freebets_route():
    with LOCK:
        return jsonify(CACHE["freebets"])

@app.route("/api/history")
def history():
    entries = load_history()
    nb      = len(entries)
    gains   = [e["gain_100"] for e in entries]
    trjs    = [e["trj"]      for e in entries]
    sports_count = {}
    for e in entries:
        sports_count[e["sport"]] = sports_count.get(e["sport"], 0) + 1
    stats = {
        "total_arbs":      nb,
        "total_gain_100":  round(sum(gains), 2) if gains else 0,
        "avg_trj":         round(sum(trjs) / nb, 3) if trjs else 0,
        "best_gain":       round(max(gains), 2) if gains else 0,
        "sports_breakdown": sports_count,
    }
    return jsonify({"entries": list(reversed(entries)), "stats": stats})

@app.route("/api/all")
def all_data():
    with LOCK:
        return jsonify({
            "kpis":               CACHE["kpis"],
            "arbitrages":         CACHE["arbitrages"],
            "freebets":           CACHE["freebets"],
            "last_update":        CACHE["last_update"],
            "status":             CACHE["status"],
            "api_key_configured": CACHE["api_key_configured"],
            "requests_remaining": CACHE["requests_remaining"],
        })


if __name__ == "__main__":
    print("=" * 60)
    print("  SportsBetting API — The Odds API")
    print("=" * 60)
    if ODDS_API_KEY:
        print(f"  Clé API  : {'*' * (len(ODDS_API_KEY)-4)}{ODDS_API_KEY[-4:]}")
    else:
        print("  ⚠  Clé API manquante")
    print(f"  Seuil    : TRJ ≥ {MIN_TRJ_RATIO*100:.1f}% (near-arbs inclus)")
    print(f"  Refresh  : toutes les {REFRESH_SEC}s")
    print(f"  Candidats: {len(SPORT_CANDIDATES)} compétitions (filtrées dynamiquement)")
    print("=" * 60)
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    print("API sur http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
