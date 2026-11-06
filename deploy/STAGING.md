# Izolovaný lokálny staging

Vyžaduje Python **3.10+** a Docker Compose **2.30.0 alebo novší**. Overlay používa oficiálny
[`!override`](https://docs.docker.com/reference/compose-file/merge/#replace-value),
ktorý nahradí celý zoznam portov a env súborov. Obyčajné zlúčenie by ponechalo
aj verejné porty základnej konfigurácie. `env_file.format: raw` zakazuje interpoláciu
URL v súkromnom súbore. `!reset` odstraňuje zdedené environment položky pre DB a Redis;
exportovaný `DATABASE_URL` ani `REDIS_URL` ich preto neprepíšu.

Samostatný executable `docker-compose` prijíma rovnaké argumenty ako nižšie uvedené
`docker compose`; môžeš ho použiť aj bez úpravy globálnej konfigurácie pluginov.

Z koreňa repozitára priprav súkromnú konfiguráciu:

```bash
cp deploy/.env.example .env.staging
chmod 600 .env.staging
```

V `.env.staging` vyplň unikátne heslo databázy, lokálny `DATABASE_URL`,
administrátorský email a heslo, a náhodný session secret s aspoň 32 znakmi.
Databázový host je lokálna služba `postgres`; heslo v URL musí byť URL-enkódované.
DSN zapíš doslova, bez úvodzoviek a bez odkazov `${...}` na iné premenné.
Používateľ, databáza a dekódované heslo musia zodpovedať `POSTGRES_*` v tom istom súbore.
Použi novú staging databázu a hodnoty nezdieľaj s produkciou. Prázdna šablóna
zámerne neprejde validáciou Compose, aby sa nepoužili predvolené prihlasovacie údaje.

Kontrola konfigurácie bez spustenia kontajnerov:

```bash
python3 deploy/staging.py check
```

Lokálny stack spúšťaj cez kontrolovaný launcher:

```bash
python3 deploy/staging.py up
```

Launcher najprv vyrenderuje Compose konfiguráciu iba do pamäte, overí lokálny
Postgres/Redis, zhodu DB credentials a režim staging. Vzdialený host, iná databáza,
neplatná konfigurácia alebo chýbajúce údaje ukončia kontrolu ešte pred `up`.
Výsledná konfigurácia ani hodnoty tajomstiev sa nevypisujú. Zdedené shellové
premenné definované stagingovou šablónou sa pre tieto príkazy odstránia.
Samostatné ručné `docker compose up` obchádza túto kontrolu cieľov.

Príkaz `up` najprv zostaví image, zastaví existujúce staging API a worker,
počká na zdravý Postgres/Redis, vykoná migrácie novým API image a až po úspechu
spustí celý stack. Počas aktualizácie stagingu je preto krátky výpadok.
Pri zlyhaní migrácie API ani worker nespustí; nedochádza k automatickému downgrade.
Výstupy fáz sa zachytávajú, aby prípadný traceback nevypísal DSN.

Projekt má vlastný
názov `straz-staging`, teda oddelené predvolené volumes a sieť. Jediné publikované
porty sú `127.0.0.1:8080` a `127.0.0.1:8443`; pôvodné verejné Compose konfigurácie
ostávajú samostatné. API aj worker čítajú iba `.env.staging`, nie koreňové `.env`.

Simulované predplatné je predvolene vypnuté. `STRAZ_ALLOW_SIMULATED_BILLING=true`
zapni iba pri potrebnej skúške na izolovanej databáze. Produkcia ho odmietne aj
s týmto nastavením; organizácie s existujúcim Stripe predplatným sa nemenia.
Stripe hodnoty ostávajú prázdne.

Pri existujúcej databáze zmena `STRAZ_ADMIN_PASSWORD` v konfigurácii nemení heslo
existujúceho účtu. To treba zmeniť samostatným podporovaným aplikačným postupom.
Kopírovanie šablóny nevykonáva rotáciu produkčných ani existujúcich údajov.
