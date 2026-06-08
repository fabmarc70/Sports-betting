"""
API Flask légère — scraping sans Selenium (compatible cloud)
Utilise requests + BeautifulSoup sur comparateur-de-cotes.fr
"""
import sys, os, io, json, threading, datetime, time, re
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CACHE = {
    "arbitrages": [], "freebets": [], "kpis": {},
    "last_update": None, "status": "initializing"
}
LOCK = threading.Lock()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

BOOKMAKERS = [
    "betclic", "winamax", "unibet", "pmu",
    "bwin", "pinnacle", "zebet", "parionssport"
]

SPORTS = ["football", "tennis", "basketball", "rugby"]

SPORT_COLORS = {
    "football": "#4f8ef7", "tennis": "#34d399",
    "basketball": "#a78bfa", "rugby": "#f59e0b"
}


def fetch_matches(sport):
    """Récupère les matchs et cotes depuis comparateur-de-cotes.fr"""
    url = f"https://www.comparateur-de-cotes.fr/comparateur/{sport}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        matches = []
        for row in soup.find_all("table", class_="bettable")[:30]:
            try:
                teams = row.find("a", class_="otn")
                if not teams:
                    continue
                name = teams.text.strip()
                odds_cells = row.find_all("td", class_="cote")
                odds_by_book = {}
                for cell in odds_cells:
                    book = cell.get("data-site", "")
                    val = cell.text.strip().replace(",", ".")
                    if book and val:
                        try:
                            odds_by_book[book] = float(val)
                        except ValueError:
                            pass
                if len(odds_by_book) >= 2:
                    matches.append({
                        "match": name,
                        "sport": sport,
                        "odds": odds_by_book
                    })
            except Exception:
                continue
        return matches
    except Exception as e:
        return []


def find_arbitrages(matches):
    """Identifie les arbitrages (TRJ > 100%) dans les matchs"""
    results = []
    for m in matches:
        odds = m["odds"]
        if len(odds) < 2:
            continue
        # Pour un match 2 issues : 1/o1 + 1/o2 < 1 = arbitrage
        # On cherche max cote sur chaque bookmaker
        books = list(odds.keys())
        max_odd = max(odds.values())
        min_odd = min(odds.values())
        if max_odd == 0 or min_odd == 0:
            continue
        # Calcul simplifié TRJ pour 2 cotes (meilleure sur chaque issue)
        # Hypothèse : match 2 issues
        sorted_odds = sorted(odds.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_odds) >= 2:
            best1 = sorted_odds[0]
            best2 = sorted_odds[-1]
            trj_inv = 1/best1[1] + 1/best2[1]
            if trj_inv < 1:
                trj = round((1/trj_inv) * 100, 3)
                gain_100 = round((1 - trj_inv) * 100 / trj_inv, 2)
                results.append({
                    "match": m["match"],
                    "sport": m["sport"],
                    "competition": "",
                    "bookmakers": f"{best1[0]} / {best2[0]}",
                    "cotes": f"{best1[1]} / {best2[1]}",
                    "trj": trj,
                    "gain_100": gain_100,
                    "date": "",
                    "status": "live"
                })
    results.sort(key=lambda x: x["trj"], reverse=True)
    return results[:20]


def refresh_loop():
    while True:
        try:
            with LOCK:
                CACHE["status"] = "refreshing"
            all_matches = []
            for sport in SPORTS:
                matches = fetch_matches(sport)
                all_matches.extend(matches)
                time.sleep(1)

            arbs = find_arbitrages(all_matches)

            # KPIs
            nb_arb = len(arbs)
            avg_trj = round(sum(a["trj"] for a in arbs) / nb_arb, 3) if nb_arb else 100.0
            gain_total = round(sum(a["gain_100"] for a in arbs), 2)

            # Freebet stubs (taux théoriques sans scraping lourd)
            freebets = [
                {"site": b, "taux": 72.0 + i * 0.5, "sport": "football", "match": ""}
                for i, b in enumerate(BOOKMAKERS[:6])
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
                    )),
                    "nb_freebets": len(freebets)
                }
                CACHE["last_update"] = datetime.datetime.now().isoformat()
                CACHE["status"] = "ok"

            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] Rafraîchi — {nb_arb} arbitrages | {len(all_matches)} matchs scannés")

        except Exception as e:
            with LOCK:
                CACHE["status"] = f"error: {e}"
            print(f"Erreur: {e}")

        time.sleep(300)


@app.route("/api/status")
def status():
    with LOCK:
        return jsonify({"status": CACHE["status"], "last_update": CACHE["last_update"]})

@app.route("/api/kpis")
def kpis():
    with LOCK:
        return jsonify(CACHE["kpis"])

@app.route("/api/arbitrages")
def arbitrages():
    with LOCK:
        return jsonify(CACHE["arbitrages"])

@app.route("/api/freebets")
def freebets():
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
            "status": CACHE["status"]
        })

if __name__ == "__main__":
    print("=" * 50)
    print("  SportsBetting API Lite - Démarrage")
    print("=" * 50)
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    print("API sur http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
