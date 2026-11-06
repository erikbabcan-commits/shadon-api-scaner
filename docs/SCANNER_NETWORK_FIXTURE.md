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
