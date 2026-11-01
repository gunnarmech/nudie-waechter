"""Nudie-Groessen-Waechter.

Fragt den Live-Bestand bei Nudie ab (dieselbe Abfrage wie der Groessenwaehler
im Shop, anonyme Sitzung, kein Konto) und schickt per ntfy eine Nachricht aufs
Handy, sobald eine der Groessen aus config.json lieferbar wird.

Aufruf:
  python waechter.py            ein Durchlauf (fuer die Windows-Aufgabe)
  python waechter.py --status   aktuellen Bestand anzeigen, nichts senden
  python waechter.py --test     Testbenachrichtigung senden
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASIS = Path(__file__).resolve().parent
CONFIG = json.loads((BASIS / "config.json").read_text(encoding="utf-8"))
# ntfy-Kanal ist geheim: lokal aus lokal.json (nicht im Repo), in der Cloud aus dem Secret
if (BASIS / "lokal.json").exists():
    CONFIG.update(json.loads((BASIS / "lokal.json").read_text(encoding="utf-8")))
if os.environ.get("NTFY_KANAL"):
    CONFIG["ntfy_kanal"] = os.environ["NTFY_KANAL"]
STATUS_DATEI = BASIS / "status.json"
LOG_DATEI = BASIS / "waechter.log"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
API = "https://nudie.dtc.centraapis.com/shop/dtc"
QUERY = """query productStocks($where: DisplayItemFilter!, $page: Int!, $limit: Int!) {
  displayItems(where: $where, limit: $limit, page: $page) {
    list { id items { sku stock { available } } }
  }
}"""
FEHLER_MELDEN_AB = 8  # so viele Fehlschlaege in Folge, dann eine Warnung aufs Handy


def log(text):
    zeile = f"{dt.datetime.now():%d.%m. %H:%M:%S} {text}"
    print(zeile)
    with LOG_DATEI.open("a", encoding="utf-8") as f:
        f.write(zeile + "\n")


def post(url, daten=None, kopf=None):
    req = urllib.request.Request(url, data=daten, method="POST",
                                 headers={"User-Agent": UA, **(kopf or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def live_bestand():
    """{sku: verfuegbar} fuer alle Groessen des Produkts."""
    token = post("https://www.nudiejeans.com/api/session")["token"]
    # Markt fest einstellen; sonst richtet er sich nach der IP (Cloud-Server stehen in den USA)
    markt = post("https://www.nudiejeans.com/api/setmarket",
                 json.dumps({"id": CONFIG["markt_id"], "token": token}).encode(),
                 {"Content-Type": "application/json"})
    if markt["session"]["market"]["id"] != CONFIG["markt_id"]:
        raise RuntimeError(f"Markt nicht umgestellt: {markt['session']['market']}")
    token = markt.get("token") or token
    variablen = {"where": {"id": [CONFIG["produkt_id"]], "onlyAvailable": False},
                 "limit": 1, "page": 1}
    antwort = post(API, json.dumps({"query": QUERY, "variables": variablen}).encode(),
                   {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    liste = antwort["data"]["displayItems"]["list"]
    if not liste:
        raise RuntimeError("Produkt nicht gefunden")
    return {i["sku"]: bool(i["stock"]["available"]) for i in liste[0]["items"]}


def sku(groesse):
    weite, laenge = groesse.upper().replace("W", "").replace("L", "").split("/")
    return f"{CONFIG['artikel']}-L{laenge}-W{weite}"


def sende(titel, text, prio="high", tags="jeans"):
    """Push aufs Handy. In GitHub Actions zusaetzlich ein Issue anlegen und dem Besitzer
    zuweisen; GitHub verschickt dazu die E-Mail (ntfy mailt nur mit Konto)."""
    kopf = {"Title": titel.encode("utf-8"), "Priority": prio, "Tags": tags, "Click": CONFIG["url"]}
    req = urllib.request.Request(f"https://ntfy.sh/{CONFIG['ntfy_kanal']}",
                                 data=text.encode("utf-8"), method="POST", headers=kopf)
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:  # ein Kanal darf den anderen nicht blockieren
        log(f"ntfy fehlgeschlagen: {e!r}")
    if os.environ.get("GITHUB_ACTIONS") and os.environ.get("GH_TOKEN"):
        issue = {"title": titel, "body": f"{text}\n\n{CONFIG['url']}",
                 "assignees": [os.environ["GITHUB_REPOSITORY_OWNER"]]}
        try:
            post(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/issues",
                 json.dumps(issue).encode(),
                 {"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                  "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
        except Exception as e:
            log(f"Issue/E-Mail fehlgeschlagen: {e!r}")


def lade_status():
    try:
        return json.loads(STATUS_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verfuegbar": {}, "fehler_in_folge": 0}


def durchlauf():
    status = lade_status()
    try:
        bestand = live_bestand()
    except Exception as e:  # Netz, API-Aenderung, Sitzung
        status["fehler_in_folge"] = status.get("fehler_in_folge", 0) + 1
        log(f"Fehler ({status['fehler_in_folge']} in Folge): {e!r}")
        if status["fehler_in_folge"] == FEHLER_MELDEN_AB:
            sende("Nudie-Waechter: Abfrage klappt nicht",
                  f"Seit {FEHLER_MELDEN_AB} Durchlaeufen Fehler. Letzter: {e!r}",
                  prio="default", tags="warning")
        STATUS_DATEI.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return

    status["fehler_in_folge"] = 0
    teile = []
    for groesse in CONFIG["groessen"]:
        s = sku(groesse)
        if s not in bestand:
            log(f"{groesse}: SKU {s} gibt es nicht")
            continue
        jetzt = bestand[s]
        vorher = status["verfuegbar"].get(groesse, False)
        teile.append(f"{groesse} {'JA' if jetzt else 'nein'}")
        if jetzt and not vorher:
            sende(f"{CONFIG['name']} {groesse} wieder da!",
                  f"Groesse {groesse} ist bei Nudie lieferbar. Tippen zum Shop.")
            log(f"{groesse}: wieder lieferbar, Nachricht gesendet")
        elif vorher and not jetzt:
            log(f"{groesse}: wieder ausverkauft")
        status["verfuegbar"][groesse] = jetzt
    log("Bestand: " + ", ".join(teile))
    STATUS_DATEI.write_text(json.dumps(status, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if "--test" in sys.argv:
        sende("Nudie-Waechter Test", "Wenn du das liest, kommen die Nachrichten an.",
              prio="default", tags="white_check_mark")
        print("Testnachricht gesendet.")
    elif "--schleife" in sys.argv:
        # Dauerlauf fuer die Cloud: jede Minute pruefen, fuer N Minuten
        minuten = int(sys.argv[sys.argv.index("--schleife") + 1])
        ende = time.monotonic() + minuten * 60
        while time.monotonic() < ende:
            start = time.monotonic()
            try:
                durchlauf()
            except Exception as e:  # nie die Schleife abbrechen
                log(f"Unerwarteter Fehler: {e!r}")
            time.sleep(max(0, 60 - (time.monotonic() - start)))
    elif "--status" in sys.argv:
        b = live_bestand()
        for g in CONFIG["groessen"]:
            print(g, "lieferbar" if b.get(sku(g)) else "nicht lieferbar")
    else:
        durchlauf()
