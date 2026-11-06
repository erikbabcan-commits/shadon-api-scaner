# Opakovateľné lokálne overenie backendu

Použi Python **3.12+** z izolovaného prostredia so závislosťami z frozen `apps/api/uv.lock`.
Produkčné URL ani prihlasovacie údaje sa runneru nezadávajú. Potrebuje nainštalované
PostgreSQL binárky (vrátane initdb/pg_ctl/createdb) a Redis server/CLI.

Z koreňa repozitára, napríklad na tomto Macu:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/straz-verification-venv uv sync --project apps/api --frozen --dev --python 3.12
/tmp/straz-verification-venv/bin/python scripts/verify_backend_local.py \
  --postgres-bin /opt/homebrew/opt/postgresql@16/bin \
  --postgres-bin /opt/homebrew/opt/postgresql@18/bin \
  --redis-server /opt/homebrew/bin/redis-server \
  --redis-cli /opt/homebrew/bin/redis-cli \
  --output /tmp/straz-verification-results
```

Výstupný adresár musí byť nový a mimo repozitára. Na Linuxe zadaj zodpovedajúce
cesty k binárkam; initdb nespúšťaj ako root. Script používa aktuálny interpreter,
nový cluster pre každú verziu PostgreSQL a nový nepersistentný Redis. Porty sú
náhodné a viazané na loopback. Existujúce lokálne ani produkčné DB sa nepoužijú.

Runner vyžaduje úspech celej sady bez preskočených testov. Počas nej sa kombinujú
SQLite API jednotkové testy, skutočné PostgreSQL migrácie/cutover a Redis quota
testy; neznamená to spustenie všetkých API testov na PostgreSQL. HTTP/DNS fixtures
zabraňujú externému skenovaniu. Toto overenie nenahrádza Linux kontajnerový tok,
aktuálne cloud CI ani produkčnú browser/iPhone akceptáciu.

Po skončení runner zastaví svoje služby a odstráni dočasné clustre. Pri zlyhanom
zastavení PG uchová cluster namiesto zmazania živých súborov. Diagnostika zostáva
v privátnych logoch; konzola nezobrazuje výstup neúspešných subprocessov. JSON
výsledok obsahuje verzie, source SHA, príznak zmien pracovného stromu a hashe
testovaných súborov. Pred zverejnením prípadných logov vykonaj sanitizáciu.

## Obnova schválenej súkromnej zálohy

`scripts/verify_restore_local.py` prijíma existujúci privátny custom-format archív
a jeho manifest (SHA-256, revízia a počty tabuliek z rovnakého zdrojového snapshotu).
Obnoví ich výhradne do nového owner-only Unix socket clusteru s TCP vypnutým,
porovná počty a hash pôvodných aplikačných riadkov, overí immutable audit, vykoná
migrácie aktuálneho kódu a porovná pôvodné dáta znovu. Výstup obsahuje iba výsledky
a hashe migračných súborov, nikdy počty/obsah produkčných riadkov alebo credentials.

```bash
/tmp/straz-verification-venv/bin/python scripts/verify_restore_local.py \
  --archive /secure/backup.dump \
  --manifest /secure/backup.manifest.json \
  --postgres-bin /opt/homebrew/opt/postgresql@18/bin \
  --output /secure/new-restore-proof.json
```

Ide o citlivú kópiu údajov: použiť iba schválený dôveryhodný archív a privátne
úložisko. Nespúšťa API, worker, notifikácie ani iné integrácie. Zdrojovú DB vôbec
nekontaktuje. Svoj cluster zastaví a pracovné dáta odstráni; archív ostáva zachovaný.
Táto skúška nepotvrdzuje produkčný upgrade ani automatickú backup/retention politiku.
