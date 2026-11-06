# Sieťová fixture pre budúci scanner runner

## Pripnuté buildy TLSX a HTTPX

`python3 scripts/build_scanner_projectdiscovery.py tlsx` alebo `httpx` je
operátorský build pre existujúci Linux AMD64 host. Prijíma iba tieto dve voľby;
oficiálny ZIP overí pripnutým SHA-256 ešte pred čítaním členov. Vyberá presný
binárny a licenčný súbor, odmieta duplicity, odkazy, zlú ELF architektúru alebo
dynamický loader. Obmedzuje veľkosť archívu/binárky a používa už lokálny,
digestom pripnutý BusyBox. Build nemá RUN, má `--network=none --pull=false`,
non-root používateľa a HOME v `/tmp`; nespúšťa aplikačné joby.

Kontrolný red beh ukázal, že samotný SOURCE_DATE_EPOCH a normalizovaný vstupný
tar nestačia: COPY vytvoril adresáre s rozdielnymi časmi vo vrstve. Aktuálny
build pridáva vlastný obmedzený filesystem tar s explicitnými časmi, UID/GID
a režimami súborov aj adresárov. Obsahuje výhradne overenú binárku a oficiálnu
licenciu; upstream archív sa na hostiteľovi nerozbaľuje.

Na lokálnom OrbStack aj vybranom VPS prešli dva `--no-cache` buildy každého
nástroja; pozorované výsledné image ID aj context SHA sa zhodujú medzi oboma
prostrediami. Nejde o záruku pre každú budúcu verziu BuildKit. Nové image:

- TLSX 1.1.9: `sha256:48867cc2dd14934d334fa3e798e320e071eff6d8858b27f7376ded5fc683f962`.
- HTTPX 1.6.10: `sha256:e1b267066bd0ecd448fce4897b28be837955c9db2199eaeb652e6ca6ec867105`.

Obe sa spustili offline/read-only/non-root. Na VPS navyše cez existujúci presný
IP/TCP guard prešla TLS sonda vlastného backendu a HTTP readiness 200.
Všetkých 14 pôvodných kontajnerov zostalo bežať. Nových 15 regresií je súčasťou
natívnej matice 450/450 na PG16 aj PG18.
[Dôkaz buildov a runtime sond](evidence/scanner-pinned-image-builds-2026-11-06.json),
[testovacia matica](evidence/backend-image-builder-matrix-2026-11-06.json).

Aktuálny builder pred sťahovaním vyžaduje aspoň 1 GiB a súčasne 5 %
voľnej kapacity Docker storage, rovnako ako critical hranica kapacitného gate.
Nič sám nečistí. Historický úspešný build nižšie používal pôvodnú hranicu
512 MiB; nové pravidlo na dnešnom VPS ďalší build zablokuje.
Cielených 17 regresií prešlo vrátane 664 MiB a 1,5 GiB na 40 GiB disku. Pred testom mal VPS približne 117 MiB: používateľ schválil presných
45 neaktívnych/nesdieľaných cache ID. Odstránilo sa 38; sedem Docker ponechal
kvôli závislostiam. Image a volumes aj bežiace služby zostali zachované.
[Dôkaz schváleného čistenia](evidence/vps-approved-cache-cleanup-2026-11-06.json).
Po nových buildoch zostalo približne 479 MiB, čo je prevádzkový nedostatok;
Po samostatnom výslovnom schválení sa odstránilo aj všetkých šesť nových
upload kontextov. Voľné miesto stúplo na 696 479 744 bajtov (približne 664 MiB);
14 kontajnerov, image a volumes zostalo zachovaných.
[Dôkaz](evidence/scanner-context-cleanup-2026-11-06.json).
Jednorazový read-only kapacitný gate pred týmto čistením potvrdil critical;
aj nový voľný priestor je pod critical hranicou približne 1,86 GiB.
[Dôkaz kontroly](evidence/scanner-storage-live-2026-11-06.json).
Tento krok neaktivuje aplikačné CLI profily a nedokazuje bezpečnosť všetkých
závislostí nástrojov. Reprodukovateľný Git/Naabu/Trivy build, DB refresh,
kapacitný monitoring a ďalšie integračné hranice zostávajú otvorené.

Read-only operátorská kontrola:
`python3 scripts/check_scanner_storage.py --path /var/lib/docker`.
Vracia JSON a exit 0 iba pri zdravom priestore, 1 pri warning/critical a 2
pri nedostupnom úložisku. Critical hranica je maximum 1 GiB a 5 % kapacity;
warning maximum 2 GiB a 10 %. Nič nemaže a nečíta obsah súborov ani env.
Lokálne boli overené zdravá/kritická fixture, reálne warning úložisko aj
nedostupná cesta. Toto je pripravený gate, nie nainštalovaný monitoring alebo
doručovanie alertov na VPS; tie stále vyžadujú prevádzkové zapojenie.

## Predchádzajúce adaptačné a izolačné dôkazy

`trivy_fs` teraz používa kontrolovaný Git HEAD archív a nový offline Trivy
0.74.0 kontajner s vopred zabudovanou reálnou Aqua vulnerability DB. Runtime
má network none, explicitný schválený YAML config, vypnuté repo ignore pravidlá,
memory scan cache a 256 MiB limit. DB schema musí byť 2; UpdatedAt nesmie byť
staršie než 72 h ani v budúcnosti o viac než 5 min, NextUpdate nesmie byť staršie
než 24 h. Chýbajúci/neplatný DB alebo report bez analyzovaných targetov zlyhá.
Scope je `supported_dependency_files`, nie úplná bezpečnosť či všetky balíky.
Výsledok nesie DB dátumy a zdrojový commit, CVE/balík/verzie/závažnosť.
Reálny test zachytil syntetickú zraniteľnú lodash závislosť; vlastný verejný
repo snapshot analyzoval 2 targety a vrátil 6 nálezov, vrátane dnspython 2.8.0.
Tieto nálezy neznamenajú, že aktuálna release vetva má rovnaké npm verzie.
[Dôkaz a presná identita](evidence/scanner-trivy-fs-live-2026-11-06.json).
DB refresh/reprodukovateľný build, širšia jazyková coverage a produkčná
aktivácia zostávajú otvorené. Skener počas jobu nič nesťahuje.

TCP connect profil `deploy/scanner_naabu.py` používa Naabu 2.6.1 výhradne
v režime `-s c`, non-root, bez capabilities a host discovery. Povolených je
1..64 explicitných portov; nft allowlist obsahuje presné IP/port páry.
Nevolá nmap, pasívne API ani raw SYN/UDP scan. Výsledok obsahuje testované
porty a pozorované otvorené porty ako info; neuvádza dôkaz zatvorených portov.
Reálny job vlastného backendu na TCP 443 prešiel cez dispatcher a receipt
replay. Release binárka potrebuje kompatibilný loader/libpcap: Alpine pokus
zlyhal, Debian bookworm/libpcap image prešiel bez zvýšenia práv.
[Dôkaz a presný image/checksum](evidence/scanner-naabu-live-2026-11-06.json).
Nejde o široký port scan ani produkčnú aktiváciu profilu.

Offline source handoff teraz prijíma iba nekomprimovaný tar do 4 MiB.
`deploy/scanner_archive.py` validuje členov bez hostiteľskej extrakcie:
odmieta traversal, absolútne/duplicitné cesty, odkazy a špeciálne súbory.
Rozbaľovanie prebehne iba v novom offline kontajneri na noexec tmpfs,
bez host bind mountu. Repo konfigurácia/ignore súbor nesmie potlačiť Gitleaks
pravidlá: explicitný config rozširuje vstavané pravidlá, ignore cesta je
`/dev/null` a allow komentáre sú vypnuté. Reálny syntetický archive scan na VPS
zachytil token aj napriek repo allowlistu a vrátil iba redigované metadáta
s relatívnou cestou súboru.
[Dôkaz](evidence/scanner-archive-live-2026-11-06.json).
Väčšie archívy a repozitáre s odkazmi zlyhajú explicitne; nevracajú čistý sken.
Priame Git → archive → offline Gitleaks prepojenie už prešlo na reálnom
verejnom repozitári a následne cez nové CLI vrátane receipt replay.
Gitleaks job môže namiesto `source_base64` prijať `repository_url` (nie oboje).
Výsledok explicitne uvádza `scope=repository_head` a nemenný commit SHA.
Git export používa prázdny worktree, aby `.gitattributes` export-ignore ani
export-subst nezmenili skenovaný snapshot. Regresia vytvára reálny lokálny Git
repozitár s export-ignore a overuje prítomnosť skrytého súboru v tar prúde.
[Reálny dôkaz celého toku](evidence/scanner-repository-chain-2026-11-06.json).
Plná história, súkromná repo autentifikácia, veľké zdroje a odkazy zostávajú
otvorené. Toto nie je produkčná aktivácia profilu.

Git acquisition command builder `deploy/scanner_git.py` prijíma iba HTTPS URL
bez credentials/query/fragmentu, explicitnú verejnú IP a pevný sandbox cieľ.
Používa `http.curloptResolve`, TLS verification, zákaz redirectov, hooks,
credential helperov a všetkých protokolov okrem HTTPS. Clone je bare a depth 1,
bez submodulov, checkoutu alebo vykonávania repozitárového kódu.
Skutočný clone vlastného verejného repozitára cez Git 2.49.1 na VPS prešiel.
[Dôkaz a rozsah](evidence/scanner-git-live-2026-11-06.json).
Zdroj opúšťa clone kontajner iba ako validovaný obmedzený tar prúd do nového
offline kontajnera. Väčšie repozitáre, plná história a reprodukovateľný Git
image zostávajú otvorené.

Jednorazové rozhranie supervisora:
`python3 deploy/scanner_job_cli.py --images-file <operátorom-spravované-images.json> --state-dir <súkromný-spoločný-stav>`.
Prijme jeden JSON zo stdin (max 2 MiB), odmietne duplicitné polia a vypíše
jeden JSON do stdout. Konfigurácia obsahuje iba nemenné lokálne image IDs.
Chyba vracia generický `scanner_job_failed`, nie tool stderr alebo zdrojové
dáta. Pracovný alarm je 300 s; cleanup môže pokračovať po tomto limite.
Bežné SIGTERM/INT/HUP rozbalia finally bloky, SIGKILL/crash recovery tým
nie sú vyriešené. Reálny nový subprocess → izolovaný kontajner prešiel.
[Dôkaz](evidence/scanner-cli-live-2026-11-06.json).
CLI neotvára port. Autentifikovaný súkromný transport a tenant admission
musia vzniknúť pred produkčným zapojením; žiadny daemon nebol nasadený.

`deploy/scanner_state.py` serializuje supervisor procesy cez OS flock v jednom
spoločnom súkromnom adresári. Durable running receipt vznikne pred spustením,
úspešný výsledok sa uloží atomicky s fsync a opakovaná rovnaká úloha sa
nevykoná znova. Hash zahŕňa vstup aj image konfiguráciu; raw source sa neukladá.
Rovnaké ID s iným vstupom/images sa odmietne. Running/failed receipt alebo
osirelé scanner kontajnery vyžadujú kontrolu operátora, nie automatický replay.
Reálny CLI replay na VPS prešiel so zhodnou odpoveďou bez prepisu receipt.
[Dôkaz](evidence/scanner-state-live-2026-11-06.json).
Nie je to automatická crash recovery ani globálny lease existujúceho ARQ
workeru. Retencia receipts, disk monitoring a riadená rekonciliácia zostávajú
potrebné pred produkčným zapojením. Všetky procesy musia používať ten istý stav.

Nový admission guard pod existujúcim flock pred vznikom nového receipt vyžaduje
na stavovom filesysteme aspoň maximum 1 GiB/5 % plus 8 MiB rezervu na výsledok
a jeho atomickú náhradu. Pri 10 000 položkách stavového adresára odmietne nové
úlohy a vyžiada operátorskú retenciu. Počíta aj neznáme a dočasné položky,
nič automaticky nemaže. Už dokončený identický replay prebehne aj pri nízkom
priestore alebo limite. Regresie overujú odmietnutie pred execute/zápisom
nového receipt a zachovanie existujúcich bajtov. Toto nie je nasadená retencia,
rezervácia filesystemu proti cudzím procesom ani záruka pri náhlom zaplnení disku.

`deploy/scanner_job.py` poskytuje verzované dôveryhodné job rozhranie pre
Gitleaks stdin/repository HEAD, TLS, obmedzené HTTP a TCP connect pozorovanie. Identita je kanonické UUID,
job nesmie vyberať príkaz, image ani env. Images sú pevná konfigurácia operátora.
Sieťový dispatch raz vyrieši DNS, odmietne akúkoľvek neverejnú odpoveď a
vyžaduje úspech všetkých adries. Čiastočný výsledok neoznačí ako kompletný.
Reálny dispatch všetkých troch adaptérov do kontajnerov na VPS prešiel;
HTTP readiness vlastného backendu vrátil 200.
[Dôkaz a presný rozsah](evidence/scanner-job-live-2026-11-06.json).
Rozhranie samo nevykonáva tenantové oprávnenia, kvóty, autentifikovaný transport
ani trvalú idempotenciu. Nie je verejná služba a nesmie sa tak vystaviť.
Tieto integračné hranice a zostávajúce adaptéry zostávajú otvorené.

HTTP pozorovanie `deploy/scanner_httpx.py` používa HTTPX 1.6.10, presnú verejnú
IP/port, explicitné Host/SNI, HTTPS bez fallbacku a bez nasledovania redirectov.
Čítanie odpovede je limitované na 128 KiB a výsledok obsahuje iba stavový kód
a prípadný server-error nález. Nevracia telo, hlavičky ani titulok stránky.
Pri reálnom teste vlastný `/healthz/readiness` vrátil 200.
128 MiB test skončil exit 137 bez reportu; následný 256 MiB beh prešiel.
Supervisor povoľuje iba pevné rozpočty 128/256 MiB, zvyšok limitov zachováva.
[Dôkaz a image checksum](evidence/scanner-httpx-live-2026-11-06.json).
Toto ešte nie je aplikačne zapnutý HTTP profil ani detekcia technológií.

`deploy/scanner_network.py` spustí dôveryhodný profilový adaptér až v guard
namespace s overenou politikou. Používa nemenné lokálne images, limitované
rúry, timeout najviac 900 s, non-root/read-only sandbox bez capabilities a
bez host mountov. Vlastný scanner kontajner odstráni pred odstránením guardu.
Reálny test na VPS porovnal identitu network namespace procesu a guardu,
overil cleanup a zachovanie pôvodných bežiacich kontajnerov.
[Dôkaz a hashe zdrojov](evidence/scanner-network-live-2026-11-06.json).
Tento test nespúšťal externý scan a neaktivuje aplikačné profily.

`deploy/scanner_tlsx.py` je prvý konkrétny sieťový adaptér: jedno autorizované
DNS meno, pripnutá verejná IP/port, explicitné SNI, zakázané update checks,
jedna paralelná úloha a limitovaný timeout. Reálny probe vlastného backendu
prešiel v izolovanom kontajneri s oficiálnym tlsx 1.1.9 overeným SHA-256.
Porovnanie názvu používa DNS SAN certifikátu a autorizovaný hostname, pretože
tool pri IP vstupe môže hlásiť mismatch voči IP aj s nastaveným SNI.
Podporovaný je presný DNS názov a celý ľavý wildcard label pre jednu úroveň.
Neplatný report alebo neúspešný probe neznamená čistý výsledok.
[Dôkaz a rozsah](evidence/scanner-tlsx-live-2026-11-06.json).
Ide o expiráciu, DNS meno a self-signed pozorovania; nie úplné overenie trust
chain/revokácie a zatiaľ ani aktivovaný aplikačný profil.

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
