"""
API Flask pour SportsBetting Dashboard
Lance avec : python api/server.py
"""
import sys
import json
import threading
import datetime
import time
import os
import pathlib

from flask import Flask, jsonify
from flask_cors import CORS

# Ajoute le dossier parent au path pour importer sportsbetting
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sportsbetting as sb
from sportsbetting.user_functions import parse_competitions
from sportsbetting.basic_functions import gain

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,OPTIONS'
    return response

HISTORY_FILE = pathlib.Path(__file__).parent / "history.json"
MAX_HISTORY = 2000

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


def compute_arbitrages():
    """Trouve les meilleures opportunités d'arbitrage dans les cotes chargées."""
    results = []
    for sport in sb.ODDS:
        for match, data in sb.ODDS[sport].items():
            try:
                odds_dict = data.get("odds", {})
                if len(odds_dict) < 2:
                    continue
                n_outcomes = len(list(odds_dict.values())[0])
                best_odds_per_outcome = []
                best_books = []
                for i in range(n_outcomes):
                    best_odd = 0
                    best_book = ""
                    for book, odds_list in odds_dict.items():
                        if len(odds_list) > i and odds_list[i] > best_odd:
                            best_odd = odds_list[i]
                            best_book = book
                    best_odds_per_outcome.append(best_odd)
                    best_books.append(best_book)

                if 0 in best_odds_per_outcome:
                    continue

                trj_val = gain(best_odds_per_outcome)
                if trj_val > 0:
                    date_obj = data.get("date")
                    date_str = date_obj.isoformat() if date_obj and date_obj != "undefined" else ""
                    trj_inv = sum(1/o for o in best_odds_per_outcome)
                    breakdown = [{"outcome": f"Issue {i+1}", "bookmaker": best_books[i], "odd": round(best_odds_per_outcome[i], 2), "stake_pct": round((1/best_odds_per_outcome[i])/trj_inv*100, 2)} for i in range(len(best_odds_per_outcome))]
                    results.append({
                        "match": match,
                        "sport": sport,
                        "competition": data.get("competition", ""),
                        "bookmakers": " / ".join(dict.fromkeys(best_books)),
                        "cotes": " / ".join(str(round(o, 2)) for o in best_odds_per_outcome),
                        "trj": round((1 + trj_val) * 100, 3),
                        "gain_100": round(trj_val * 100, 2),
                        "date": date_str,
                        "status": "live",
                        "breakdown": breakdown,
                    })
            except Exception:
                continue

    results.sort(key=lambda x: x["trj"], reverse=True)
    return results[:20]


def compute_freebets():
    return []


def refresh_loop():
    """Boucle de rafraîchissement toutes les 5 minutes."""
    while True:
        try:
            with CACHE_LOCK:
                CACHE["status"] = "refreshing"

            BOOKMAKERS = ["betclic", "winamax", "unibet", "pmu", "bwin", "parionssport", "zebet", "netbet"]
            COMPETITIONS = {
                "football": ["Ligue des Nations", "Coupe du Monde des Clubs", "Copa America", "Copa Libertadores", "Ligue Europa"],
                "basketball": ["Etats-Unis - NBA"],
                "tennis": ["tennis"],
            }
            print("  Chargement des cotes bookmakers (Chrome)...")
            for sport, competitions in COMPETITIONS.items():
                try:
                    print(f"  Scan {sport}: {competitions}...")
                    parse_competitions(competitions, sport, *BOOKMAKERS)
                    print(f"    → {len(sb.ODDS.get(sport, {}))} matchs chargés pour {sport}")
                except Exception as e:
                    print(f"    Erreur {sport}: {e}")

            arbs = compute_arbitrages()
            fbs = compute_freebets()
            total_gain = sum(a["gain_100"] for a in arbs)
            avg_trj = (sum(a["trj"] for a in arbs) / len(arbs)) if arbs else 100.0

            with CACHE_LOCK:
                CACHE["arbitrages"] = arbs
                CACHE["freebets"] = fbs
                CACHE["kpis"] = {
                    "nb_arbitrages": len(arbs),
                    "gain_potentiel": round(total_gain, 2),
                    "trj_moyen": round(avg_trj, 3),
                    "nb_bookmakers": len(set(b for a in arbs for b in a["bookmakers"].split(" / "))) if arbs else 0,
                    "nb_freebets": len(fbs)
                }
                CACHE["last_update"] = datetime.datetime.now().isoformat()
                CACHE["status"] = "ok"

            snapshot_time = datetime.datetime.now().isoformat()
            added = append_to_history(arbs, snapshot_time)
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] Rafraîchi — {len(arbs)} arbitrages | +{added} historique")

        except Exception as e:
            with CACHE_LOCK:
                CACHE["status"] = f"error: {str(e)}"
            print(f"Erreur refresh: {e}")
            import traceback; traceback.print_exc()

        time.sleep(300)


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
    with CACHE_LOCK:
        return jsonify({
            "kpis": CACHE["kpis"],
            "arbitrages": CACHE["arbitrages"],
            "freebets": CACHE["freebets"],
            "last_update": CACHE["last_update"],
            "status": CACHE["status"],
            "api_key_configured": True,
            "requests_remaining": "N/A"
        })


@app.route("/api/history")
def history():
    entries = load_history()
    nb = len(entries)
    gains = [e["gain_100"] for e in entries]
    trjs = [e["trj"] for e in entries]
    sports_count = {}
    for e in entries:
        sports_count[e["sport"]] = sports_count.get(e["sport"], 0) + 1
    stats = {
        "total_arbs": nb,
        "total_gain_100": round(sum(gains), 2) if gains else 0,
        "avg_trj": round(sum(trjs) / nb, 3) if trjs else 0,
        "best_gain": round(max(gains), 2) if gains else 0,
        "sports_breakdown": sports_count,
    }
    return jsonify({"entries": list(reversed(entries)), "stats": stats})


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
