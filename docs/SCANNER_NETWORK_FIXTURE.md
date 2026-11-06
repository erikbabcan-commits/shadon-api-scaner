# Sieťová fixture pre budúci scanner runner

`deploy/scanner_network.py` spustí dôveryhodný profilový adaptér až v guard
namespace s overenou politikou. Používa nemenné lokálne images, limitované
rúry, timeout najviac 900 s, non-root/read-only sandbox bez capabilities a
bez host mountov. Vlastný scanner kontajner odstráni pred odstránením guardu.
Reálny test na VPS porovnal identitu network namespace procesu a guardu,
overil cleanup a zachovanie pôvodných bežiacich kontajnerov.
[Dôkaz a hashe zdrojov](evidence/scanner-network-live-2026-11-06.json).
Tento test nespúšťal externý scan a neaktivuje aplikačné profily.

Offline procesná vrstva je v `deploy/scanner_process.py` a
`deploy/scanner_offline.py`: vstup najviac 1 MiB, spoločný limit stdout/stderr,
deadline aj pri zdedených alebo zavretých rúrach, ukončenie procesnej skupiny
a odstránenie kontajnerov podľa jedinečného vlastníckeho labelu. Offline
kontajner má `network=none`, nemenný lokálny image, read-only root, non-root
používateľa, zahodené capabilities a obmedzené CPU/RAM/PID. Rozhranie je iba
pre dôveryhodný host supervisor, nie pre príkazy z tenantového HTTP vstupu.
Regresné testy overujú reálne lokálne procesy a mockované Docker riadenie.
Navyše reálny Docker na zvolenom VPS prešiel syntetickým stdin roundtripom,
timeoutom, prekročením výstupu aj cleanupom; pôvodné kontajnery zostali bežať.
[Dôkaz a hashe zdrojov](evidence/scanner-offline-live-2026-11-06.json).
Samostatne prešiel aj Gitleaks 8.30.1 v reálnom offline kontajneri:
čistý stdin a detekcia syntetického tokenu, allowlist výsledných metadát bez
hodnoty tajomstva a odstránenie vlastných kontajnerov.
[Dôkaz, release checksum a image ID](evidence/scanner-gitleaks-live-2026-11-06.json).
Adaptér `deploy/scanner_gitleaks.py` nevracia zdrojový text, cestu, fingerprint
ani voľný opis z reportu. Chybný JSON, zlyhanie nástroja a nekonzistentný exit
kód znamenajú chybu. Získanie Git repozitára a aktivácia aplikačných profilov
zostávajú otvorené; stdin fixture nepreukazuje sken celej Git histórie.
Opakovateľný test na schválenom Linux Docker hoste:
`python3 scripts/verify_scanner_gitleaks.py --image-id sha256:<schválený-lokálny-image>`.
Image musí už existovať; skript nič nesťahuje a nespúšťa produkčné joby.
Na schválenom Linux AMD64 hoste ho pripraví
`python3 scripts/build_scanner_gitleaks.py`: oficiálny release 8.30.1,
pevný SHA-256, obmedzená veľkosť downloadu, extrakcia iba regulárneho binárneho
súboru, lokálny digestom pinovaný BusyBox základ bez pullu a build bez siete.
Builder ani verifier neaktivujú profily aplikácie. Oba skripty boli spolu
reálne spustené na zvolenom VPS 2026-11-06; čistý vstup, syntetický nález,
redakcia výsledku aj zachovanie pôvodných bežiacich kontajnerov prešli.

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
