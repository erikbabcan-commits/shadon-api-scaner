# Izolovaný lokálny staging

Vyžaduje Docker Compose **2.24.4 alebo novší**. Overlay používa oficiálny
[`!override`](https://docs.docker.com/reference/compose-file/merge/#replace-value),
ktorý nahradí celý zoznam portov a env súborov. Obyčajné zlúčenie by ponechalo
aj verejné porty základnej konfigurácie.

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
Použi novú staging databázu a hodnoty nezdieľaj s produkciou. Prázdna šablóna
zámerne neprejde validáciou Compose, aby sa nepoužili predvolené prihlasovacie údaje.

Kontrola konfigurácie bez spustenia kontajnerov:

```bash
docker compose --env-file .env.staging \
  -f deploy/docker-compose.yml -f deploy/docker-compose.staging.yml config --quiet
```

Lokálny stack spúšťaj s oboma súbormi a rovnakým env súborom. Projekt má vlastný
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
