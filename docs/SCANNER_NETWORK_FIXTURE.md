# Sieťová fixture pre budúci scanner runner

`deploy/scanner_policy.py` kompiluje presné verejné IP/TCP port páry, nie ich
kartézsky súčin. DNS, nesúvisiace ciele a ostatná komunikácia nemajú povolenie.
Pravidlá sú určené výhradne do nového job network namespace pred štartom skenera,
ktorý nedostane NET_ADMIN ani možnosť pravidlá meniť. Neaplikovať na host firewall.

`scripts/verify_scanner_egress.py` sa spúšťa iba cez `unshare --net`, odmietne
host namespace a vytvorí ďalší dočasný namespace s lokálnym TCP prijímačom.
Veth aj všetky zdanlivo verejné cieľové IP sú iba v tejto izolovanej fixture.
Pred aplikovaním politiky musí byť každý cieľ dostupný. Až potom sa kontroluje
povolený pár a štyri zakázané prípady. Procesy sa ukončia a namespaces zaniknú.

Na vybranom VPS prešlo šesť kontrol skutočných IPv4 TCP spojení, doložených v
[sanitizovanom výsledku](evidence/scanner-egress-wire-2026-11-06.json).
Host sieť, existujúce služby ani firewall sa nemenili. Test nie je aktivácia
scannera, IPv6 packet proof, DNS rebinding end-to-end skúška alebo hotový runner.
Ďalší krok je supervisor, ktorý pripraví job namespace, overí jeho politiku a
až potom v ňom spustí skener bez práv, secrets a prístupu ku control plane.

## Overený životný cyklus guard kontajnera

`deploy/scanner_guard.py` teraz vytvára iba vlastný non-root guard cez nemenné
lokálne image ID. Pred odovzdaním handle kontroluje vlastnícky UUID label,
container ID/image ID, bežiaci PID, sieťový režim a kernel politiku. Namespace
FD chráni pred prepnutím cieľa pri zániku/opätovnom použití PID. Aj neisté
zlyhanie Docker run má cleanup podľa vlastného unikátneho labelu.

Na vybranom VPS prešiel reálny guard lifecycle s oficiálnym BusyBox image,
64 MiB limitom a UID10001; politika sa aplikovala iba do guard namespace.
Guard bol odstránený a pôvodné bežiace kontajnery zostali zachované.
[Výsledok a nemenný digest](evidence/scanner-guard-live-2026-11-06.json).

Tento výsledok ešte nepotvrdzuje job RPC, spustenie skenovacieho kontajnera,
DNS/hosts pinning jednotlivých nástrojov, bounded repository/image fetch ani
bezpečné spracovanie výsledkov. Preto sa dostupnosť ôsmich profilov nemení.
