"""
API Flask pour SportsBetting Dashboard
Lance avec : python api/server.py
"""
import sys
import io
import json
import threading
import datetime
import time
import os

from flask import Flask, jsonify
from flask_cors import CORS

# Ajoute le dossier parent au path pour importer sportsbetting
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sportsbetting as sb
from sportsbetting.user_functions import (
    best_match_under_conditions, best_match_freebet,
    best_matches_freebet2
)
from sportsbetting.basic_functions import gain
from sportsbetting.interface_functions import trj_with_min_odd

app = Flask(__name__)
CORS(app)  # Autorise les requêtes depuis Vercel

# Cache des résultats (mis à jour en arrière-plan)
CACHE = {
    "odds": {},
    "arbitrages": [],
    "freebets": [],
    "kpis": {},
    "last_update": None,
    "status": "initializing"
}
CACHE_LOCK = threading.Lock()


def compute_arbitrages():
    """Trouve les meilleures opportunités d'arbitrage dans les cotes chargées."""
    results = []
    for sport in sb.ODDS:
        for match, data in sb.ODDS[sport].items():
            try:
                odds_dict = data.get("odds", {})
                if len(odds_dict) < 2:
                    continue
                # Calcule le TRJ
                best_odds_per_outcome = []
                best_books = []
                n_outcomes = len(list(odds_dict.values())[0])
                for i in range(n_outcomes):
                    best_odd = 0
                    best_book = ""
                    for book, odds_list in odds_dict.items():
                        if odds_list[i] > best_odd:
                            best_odd = odds_list[i]
                            best_book = book
                    best_odds_per_outcome.append(best_odd)
                    best_books.append(best_book)

                if 0 in best_odds_per_outcome:
                    continue

                trj = gain(best_odds_per_outcome)
                if trj > 0:  # TRJ > 100%
                    date_obj = data.get("date")
                    date_str = date_obj.strftime("%d/%m %H:%M") if date_obj and date_obj != "undefined" else "?"
                    results.append({
                        "match": match,
                        "sport": sport,
                        "competition": data.get("competition", ""),
                        "bookmakers": " / ".join(dict.fromkeys(best_books)),
                        "cotes": " / ".join(str(round(o, 2)) for o in best_odds_per_outcome),
                        "trj": round((1 + trj) * 100, 3),
                        "gain_100": round(trj * 100, 2),
                        "date": date_str,
                        "status": "live"
                    })
            except Exception:
                continue

    results.sort(key=lambda x: x["trj"], reverse=True)
    return results[:20]


def compute_freebets():
    """Calcule les meilleurs taux de conversion freebet par bookmaker."""
    results = []
    sports_available = [s for s in sb.ODDS if sb.ODDS[s]]
    if not sports_available:
        return results

    for site in sb.BOOKMAKERS[:8]:  # Top 8 bookmakers
        best_rate = 0
        best_sport = ""
        best_match = ""
        for sport in sports_available:
            try:
                old_stdout = sys.stdout
                sys.stdout = buf = io.StringIO()
                best_match_freebet(site, 100, sport)
                sys.stdout = old_stdout
                output = buf.getvalue()
                if "No match found" in output or not output.strip():
                    continue
                # Extrait le taux depuis la sortie
                for line in output.split("\n"):
                    if "Taux" in line or "taux" in line or "%" in line:
                        import re
                        match_rate = re.search(r'(\d+\.?\d*)\s*%', line)
                        if match_rate:
                            rate = float(match_rate.group(1))
                            if rate > best_rate:
                                best_rate = rate
                                best_sport = sport
                                best_match = output.split("\n")[0]
            except Exception:
                pass

        if best_rate > 0:
            results.append({
                "site": site,
                "taux": round(best_rate, 1),
                "sport": best_sport,
                "match": best_match[:40] if best_match else ""
            })

    results.sort(key=lambda x: x["taux"], reverse=True)
    return results


def refresh_loop():
    """Boucle de rafraîchissement toutes les 5 minutes."""
    while True:
        try:
            with CACHE_LOCK:
                CACHE["status"] = "refreshing"

            # Charge les cotes pour tous les sports
            for sport in ["football", "tennis", "basketball", "rugby"]:
                try:
                    old_stdout = sys.stdout
                    sys.stdout = io.StringIO()
                    best_match_under_conditions(
                        "betclic", 1.01, 100, sport,
                        one_site=False
                    )
                    sys.stdout = old_stdout
                except Exception:
                    sys.stdout = old_stdout

            arbs = compute_arbitrages()
            fbs = compute_freebets()

            # KPIs
            total_gain = sum(a["gain_100"] for a in arbs)
            avg_trj = (sum(a["trj"] for a in arbs) / len(arbs)) if arbs else 100.0

            with CACHE_LOCK:
                CACHE["arbitrages"] = arbs
                CACHE["freebets"] = fbs
                CACHE["kpis"] = {
                    "nb_arbitrages": len(arbs),
                    "gain_potentiel": round(total_gain, 2),
                    "trj_moyen": round(avg_trj, 3),
                    "nb_bookmakers": len(set(
                        b for a in arbs for b in a["bookmakers"].split(" / ")
                    )),
                    "nb_freebets": len(fbs)
                }
                CACHE["last_update"] = datetime.datetime.now().isoformat()
                CACHE["status"] = "ok"

            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Rafraîchi — {len(arbs)} arbitrages trouvés")

        except Exception as e:
            with CACHE_LOCK:
                CACHE["status"] = f"error: {str(e)}"
            print(f"Erreur refresh: {e}")

        time.sleep(300)  # 5 minutes


# ── Routes ──────────────────────────────────────────────

@app.route("/api/status")
def status():
    with CACHE_LOCK:
        return jsonify({
            "status": CACHE["status"],
            "last_update": CACHE["last_update"]
        })


@app.route("/api/kpis")
def kpis():
    with CACHE_LOCK:
        return jsonify(CACHE["kpis"])


@app.route("/api/arbitrages")
def arbitrages():
    with CACHE_LOCK:
        return jsonify(CACHE["arbitrages"])


@app.route("/api/freebets")
def freebets():
    with CACHE_LOCK:
        return jsonify(CACHE["freebets"])


@app.route("/api/all")
def all_data():
    """Endpoint unique pour tout récupérer en une requête."""
    with CACHE_LOCK:
        return jsonify({
            "kpis": CACHE["kpis"],
            "arbitrages": CACHE["arbitrages"],
            "freebets": CACHE["freebets"],
            "last_update": CACHE["last_update"],
            "status": CACHE["status"]
        })


if __name__ == "__main__":
    print("=" * 50)
    print("  SportsBetting API - Démarrage")
    print("=" * 50)
    print("Lancement du rafraîchissement en arrière-plan...")

    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    print("API disponible sur http://localhost:5000")
    print("Arrêter avec Ctrl+C")
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)
