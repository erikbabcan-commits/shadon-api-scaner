# STRÁŽ — kontrolovaný release Railway + Vercel

Tento postup je konfigurácia a checklist, nie dôkaz nasadenia. Staršie odhady
„nasadenie do 3 minút“ ani úspešný build nepotvrdzujú celú produkčnú pripravenosť.

## Existujúce prostredie

Railway projekt `dev-new`, služby `straz-api`, `straz-worker`, PostgreSQL a Redis. Názvy overiť; nevytvárať duplicity.
Vercel scope `h4ck3d`, projekt `straz-monitoring`.
Verejné URL sú v NOTION_NOTES.md; interné DSN ani heslá do dokumentácie nepatria.

## Pred release

- Rotáciu kompromitovaných hodnôt rieši INCIDENT_ROTATION_RUNBOOK.md. Zmena main ju nevykoná.
- Vyžadovať zelený secret gate, backend CI na PG 16/18, frontend testy, TypeScript a build.
- Skontrolovať zálohu/restore a oprávnenia podľa OPERATIONS_ACCEPTANCE.md.
- Osem CLI profilov ponechať blokovaných; dostupné sú Heartbeat a InternetDB.

## Nastavenie služieb

Root pre API/worker: apps/api. Dockerfile API: Dockerfile; worker: worker.Dockerfile.
Pre-deploy API: python -m app.migrations upgrade. Štart a health definujú
apps/api/railway.api.json a railway.worker.json. Ak platforma pre nový projekt vyžaduje
IaC alebo nastavenia cez API, nastaviť ekvivalent a overiť efektívny config deploymentu;
existencia súboru automaticky nedokazuje jeho použitie.
API aj worker kontrolujú Alembic head. Worker nasadiť až po úspešnej migrácii.
DATABASE_URL/REDIS_URL previazať na privátne služby; nevystavovať verejné DB porty.
Produkčné cookie/CORS/frontend nastavenia určuje operátor. STRAZ_TRUSTED_PROXY_IPS
nastaviť iba podľa overeného ingressu; nepoužiť wildcard. Hodnoty tajomstiev nevypisovať.

## Frontend a overenie

Na vercel.app klient používa relatívne /api a rewrite na Railway. VITE_API_URL je
verejná build konfigurácia pre iné hosty, nikdy úložisko backendových tajomstiev.
CSP je v tomto PR iba Report-Only. Pre enforcement je nutný schválený preview/browser test.

Po schválenom deployi overiť HTTPS liveness/readiness, DB aj Redis, HSTS, preflight,
401 bez cookie, autorizovaný login/logout, scope a tenantové hranice a worker.
POST kontroly, seed a testovací beh zapisujú, preto vyžadujú povolenie.
API checklist nie je browser E2E a nenahrádza iPhone/Safari/PWA test.
Pri commit pine deploy riadi operátor a push do main ho sám neaktualizuje.

Výsledok release má obsahovať skutočne nasadené SHA API/workera/frontendu,
vlastné výstupy kontrol a výslovne označené neoverené oblasti.
