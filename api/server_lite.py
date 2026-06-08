"""
API Flask — arbitrages sportifs via The Odds API (gratuit, 500 req/mois)
Inscription gratuite sur https://the-odds-api.com pour obtenir une clé API.
Lancez avec : python api/server_lite.py
Configurez votre clé dans la variable ODDS_API_KEY ci-dessous ou via variable d'environnement.
"""
import os, json, threading, datetime, time
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
# CONFIGURATION — mettez votre clé API ici
# Inscription gratuite : https://the-odds-api.com
# ─────────────────────────────────────────────
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "2dd8f5e82d2c99c2950e7c9aae554d22")

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Groupes de sports — le premier disponible dans chaque groupe est utilisé
SPORT_GROUPS = {
    "football":   ["soccer_france_ligue1", "soccer_epl", "soccer_uefa_champs_league",
                   "soccer_spain_la_liga", "soccer_germany_bundesliga", "soccer_italy_serie_a"],
    "basketball": ["basketball_euroleague", "basketball_nba", "basketball_ncaab"],
    "tennis":     ["tennis_atp_french_open", "tennis_atp_wimbledon", "tennis_atp_us_open",
                   "tennis_wta_us_open"],
}

BOOKMAKERS_FR = [
    "betclic", "unibet_fr", "winamax", "pmu_fr",
    "bwin", "pinnacle", "zebet", "parionssport"
]

CACHE = {
    "arbitrages": [], "freebets": [], "kpis": {},
    "last_update": None, "status": "initializing",
    "api_key_configured": False, "requests_remaining": "?"
}
LOCK = threading.Lock()


def fetch_odds(sport_key):
    """Récupère les cotes depuis The Odds API pour un sport donné."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 401:
            print("  ERREUR: Clé API invalide ou manquante. Inscrivez-vous sur https://the-odds-api.com")
            return None, "invalid_key"
        if r.status_code == 422:
            print(f"  Sport non disponible: {sport_key}")
            return [], "ok"
        if r.status_code == 429:
            print("  Quota API épuisé pour ce mois.")
            return None, "quota"
        remaining = r.headers.get("x-requests-remaining", "?")
        data = r.json()
        if not isinstance(data, list):
            print(f"  Réponse inattendue: {data}")
            return [], remaining
        return data, remaining
    except Exception as e:
        print(f"  Erreur réseau: {e}")
        return None, "error"


def parse_matches(events, sport_name):
    """Convertit les événements Odds API en liste de matchs avec cotes par bookmaker."""
    matches = []
    for ev in events:
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        match_name = f"{home} vs {away}"
        odds_by_book = {}
        for bm in ev.get("bookmakers", []):
            key = bm.get("key", "")
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                # On prend la cote domicile (index 0) comme référence principale
                if outcomes:
                    odds_by_book[key] = {o["name"]: o["price"] for o in outcomes}
        if len(odds_by_book) >= 2:
            matches.append({
                "match": match_name,
                "sport": sport_name,
                "date": ev.get("commence_time", ""),
                "odds_full": odds_by_book,  # {bookmaker: {team: cote}}
            })
    return matches


def find_arbitrages(matches):
    """Détecte les arbitrages sur matchs 2 ou 3 issues."""
    results = []
    for m in matches:
        odds_full = m["odds_full"]
        if len(odds_full) < 2:
            continue

        # Rassemble toutes les équipes (issues)
        all_teams = set()
        for bm_odds in odds_full.values():
            all_teams.update(bm_odds.keys())
        all_teams = list(all_teams)

        if len(all_teams) not in (2, 3):
            continue

        # Pour chaque issue, trouve la meilleure cote parmi tous les bookmakers
        best_per_outcome = {}
        for team in all_teams:
            best_odd = 0
            best_bm = ""
            for bm, bm_odds in odds_full.items():
                if team in bm_odds and bm_odds[team] > best_odd:
                    best_odd = bm_odds[team]
                    best_bm = bm
            if best_odd > 0:
                best_per_outcome[team] = (best_bm, best_odd)

        if len(best_per_outcome) < len(all_teams):
            continue

        # Calcul TRJ inverse
        trj_inv = sum(1 / v[1] for v in best_per_outcome.values())
        if trj_inv < 1.0:
            trj = round(100 / trj_inv, 3)
            gain_100 = round((1 / trj_inv - 1) * 100, 2)
            bookmakers_str = " / ".join(set(v[0] for v in best_per_outcome.values()))
            cotes_str = " / ".join(f"{v[1]}" for v in best_per_outcome.values())
            results.append({
                "match": m["match"],
                "sport": m["sport"],
                "competition": "",
                "bookmakers": bookmakers_str,
                "cotes": cotes_str,
                "trj": trj,
                "gain_100": gain_100,
                "date": m.get("date", ""),
                "status": "live"
            })

    results.sort(key=lambda x: x["trj"], reverse=True)
    return results[:20]


def refresh_loop():
    while True:
        if not ODDS_API_KEY:
            with LOCK:
                CACHE["status"] = "no_api_key"
                CACHE["api_key_configured"] = False
            print("="*55)
            print("  CONFIGURATION REQUISE")
            print("  1. Inscrivez-vous gratuitement sur https://the-odds-api.com")
            print("  2. Copiez votre clé API")
            print("  3. Ouvrez api/server_lite.py et remplacez:")
            print('     ODDS_API_KEY = ""')
            print("     par:")
            print('     ODDS_API_KEY = "votre_cle_ici"')
            print("  4. Relancez ce script")
            print("="*55)
            time.sleep(30)
            continue

        try:
            with LOCK:
                CACHE["status"] = "refreshing"
                CACHE["api_key_configured"] = True

            all_matches = []
            remaining = "?"
            stop = False
            for sport_name, sport_keys in SPORT_GROUPS.items():
                if stop:
                    break
                for sport_key in sport_keys:
                    print(f"  Scan {sport_name} ({sport_key})...")
                    events, rem = fetch_odds(sport_key)
                    if events is None:
                        if rem == "invalid_key":
                            with LOCK:
                                CACHE["status"] = "invalid_key"
                            stop = True
                        break
                    remaining = rem
                    matches = parse_matches(events, sport_name)
                    if matches:
                        all_matches.extend(matches)
                        print(f"    → {len(matches)} matchs")
                        break  # Sport trouvé, passe au groupe suivant
                    else:
                        print(f"    → 0 matchs, essai suivant...")
                    time.sleep(1)  # Respecte le rate limit

            arbs = find_arbitrages(all_matches)
            nb_arb = len(arbs)
            avg_trj = round(sum(a["trj"] for a in arbs) / nb_arb, 3) if nb_arb else 100.0
            gain_total = round(sum(a["gain_100"] for a in arbs), 2)

            freebets = [
                {"site": b.replace("_fr", ""), "taux": 70.0 + i * 1.5, "sport": "football", "match": ""}
                for i, b in enumerate(BOOKMAKERS_FR[:6])
            ]

            with LOCK:
                CACHE["arbitrages"] = arbs
                CACHE["freebets"] = freebets
                CACHE["kpis"] = {
                    "nb_arbitrages": nb_arb,
                    "gain_potentiel": gain_total,
                    "trj_moyen": avg_trj,
                    "nb_bookmakers": len(set(
                        b for a in arbs for b in a["bookmakers"].split(" / ")
                    )) if arbs else 0,
                    "nb_freebets": len(freebets)
                }
                CACHE["last_update"] = datetime.datetime.now().isoformat()
                CACHE["status"] = "ok"
                CACHE["requests_remaining"] = remaining

            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] Rafraîchi — {nb_arb} arbitrages | {len(all_matches)} matchs | Quota restant: {remaining}/mois")

        except Exception as e:
            with LOCK:
                CACHE["status"] = f"error: {e}"
            print(f"Erreur: {e}")

        time.sleep(300)  # Refresh toutes les 5 minutes


@app.route("/api/status")
def status():
    with LOCK:
        return jsonify({
            "status": CACHE["status"],
            "last_update": CACHE["last_update"],
            "api_key_configured": CACHE["api_key_configured"],
            "requests_remaining": CACHE["requests_remaining"]
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

@app.route("/api/all")
def all_data():
    with LOCK:
        return jsonify({
            "kpis": CACHE["kpis"],
            "arbitrages": CACHE["arbitrages"],
            "freebets": CACHE["freebets"],
            "last_update": CACHE["last_update"],
            "status": CACHE["status"],
            "api_key_configured": CACHE["api_key_configured"],
            "requests_remaining": CACHE["requests_remaining"]
        })


if __name__ == "__main__":
    print("=" * 55)
    print("  SportsBetting API — The Odds API")
    print("=" * 55)
    if not ODDS_API_KEY:
        print("  ⚠  Clé API manquante — consultez les instructions ci-dessous")
    else:
        print(f"  Clé API: {'*' * (len(ODDS_API_KEY)-4)}{ODDS_API_KEY[-4:]}")
    print(f"  Sports actifs: {', '.join(ACTIVE_SPORTS)}")
    print("=" * 55)
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    print("API sur http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
