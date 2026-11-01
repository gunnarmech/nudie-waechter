# Nudie-Wächter

Prüft jede Minute den Live-Bestand bei Nudie und schickt per ntfy eine Nachricht aufs
Handy, sobald eine Größe aus `config.json` lieferbar wird. Gemeldet wird nur der Wechsel
von "nicht lieferbar" auf "lieferbar", also keine Wiederholungen. Kein Konto, kein Login.

Die Abfrage ist dieselbe, die der Größenwähler im Shop benutzt (anonyme Sitzung über
`/api/session`, dann Bestand über die Centra-Schnittstelle). Der Bestand im Seitencode
der Produktseite ist dagegen oft veraltet und taugt nicht als Quelle.

## Handy einrichten

1. App **ntfy** installieren (Android: Play Store, iPhone: App Store).
2. In der App auf **+** tippen und den Kanal aus `lokal.json` (`ntfy_kanal`) abonnieren.
   Der Kanal ist geheim: lokal in `lokal.json` (nicht im Repo), in der Cloud als Secret `NTFY_KANAL`.
3. Benachrichtigungen für die App erlauben.

## Bedienung

- Aktueller Bestand: `python waechter.py --status`
- Testnachricht: `python waechter.py --test`
- Log: `waechter.log`
- Größen ändern: `groessen` in `config.json`, Format `W33/L36`
- Anderes Nudie-Produkt: `produkt_id` und `artikel` aus dem Seitencode der Produktseite
- Anhalten: `Disable-ScheduledTask -TaskName Nudie-Waechter`
- Ganz entfernen: `Unregister-ScheduledTask -TaskName Nudie-Waechter -Confirm:$false`

Schlägt die Abfrage 8 Mal in Folge fehl (etwa weil Nudie die Schnittstelle ändert),
kommt eine Warnung aufs Handy. Läuft nur, solange der PC an ist und nicht im Ruhezustand.

## Cloud (GitHub Actions)

Läuft zusätzlich im öffentlichen Repository `gunnarmech/nudie-waechter`
(`.github/workflows/waechter.yml`), unabhängig vom PC. Öffentlich, weil Actions dort
unbegrenzt kostenlos ist. Ein Lauf prüft knapp 6 Stunden lang jede Minute; der stündliche
Zeitplan stellt den nächsten Lauf in die Warteschlange, damit keine Lücke entsteht. Der letzte
Stand wird im Actions-Cache gehalten. Der Markt ist fest auf Europa EU (`markt_id` 27)
gestellt, weil die Server in den USA stehen.

E-Mail: Wird eine Größe lieferbar, legt der Cloud-Lauf sofort ein Issue an und weist es dem
Kontoinhaber zu. GitHub schickt dazu eine Mail an gunnarmech@gmail.com. (ntfy verschickt
E-Mails nur noch mit eigenem Konto.)

- Läufe ansehen: `gh run list -R gunnarmech/nudie-waechter`
- Test für Push und E-Mail: `gh workflow run waechter.yml -R gunnarmech/nudie-waechter -f test=true`
- Anhalten: `gh workflow disable waechter.yml -R gunnarmech/nudie-waechter` und laufenden Lauf mit `gh run cancel` beenden
