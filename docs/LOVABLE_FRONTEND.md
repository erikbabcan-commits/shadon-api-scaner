# STRÁŽ — frontend v Lovable, backend na Hetzneri

Stav k 5. 11. 2026. Zdroj frontendu: `apps/web` z `main@ce12ee5`.
Toto je handoff a akceptačný postup; Lovable projekt sa týmto dokumentom nevytvoril.

## Čo preniesť

Frontend obsahuje React/Vite PWA, TanStack Router/Query/Table, login/registráciu,
prehľad, aplikácie a ciele, behy, nálezy, CVSS, reporty, tím, audit, integrácie a billing obrazovku.
Zachovať existujúce stránky a API adapter `src/lib/api.ts`; nebudovať len vizuálny dashboard.

Pre frontendový ZIP dať **obsah apps/web do koreňa**:
`package.json`, `package-lock.json`, `index.html`, `src/`, `public/`,
`tsconfig.json`, `vite.config.ts` a sanitizovanú konfiguráciu.
Vlastný frontendový tsconfig je samostatný; nepotrebuje koreňový monorepo tsconfig.
Neprebaliť databázu, `.env`, cookies, export používateľov, backendové tajomstvá,
`node_modules`, `dist` ani Git históriu.

## Dôležitá hranica importu

[Lovable GitHub dokumentácia](https://docs.lovable.dev/integrations/github) uvádza:

- Git sync vytvorí nové repo pre Lovable projekt; nepripája ľubovoľné existujúce repo ako import.
- Existujúci kód sa dá načítať cez ZIP / Upload code.
- Sync pracuje s jednou zvolenou vetvou; tá sa vyberá v Project settings → Git → GitHub.

[ZIP import](https://docs.lovable.dev/features/projects/import-project) je migrácia zo zdroja:
štandardne prestavuje aplikáciu na TanStack Start a presúva DB aj prihlasovanie do vlastného backendu.
**Nie je to záruka zachovania tejto Vite aplikácie alebo externého auth.**

Pre požadované rozdelenie preto použiť frontendový balík a výslovne ponechať:
FastAPI auth, organizácie, API zmluvu, ARQ worker aj databázu na externom backende.
Nevkladať kompletný monorepo ani export dát s očakávaním automatického presunu na Hetzner.
Pred prijatím importu skontrolovať diff; prípadné TanStack Start SSR zmeny nesmú pristupovať
k localStorage/window počas server renderu ani meniť session model bez implementácie.
Ak importer tieto hranice nezachová, výsledok nie je prijatý a nepublikuje sa.

Po vytvorení a kontrole frontendu pripojiť Git sync pod zvoleným účtom
`erikbabcan-commits`, zaznamenať skutočne vytvorené repo a aktívnu vetvu.
Kanonický backend ostáva v `shadon-api-scaner`; frontendové zmeny medzi repozitármi
prenášať cez kontrolovaný commit/PR s uvedením zdrojového SHA, nie automatickým prepisom histórie.

## API, cookies a domény

| Hostovanie frontendu | Potrebné smerovanie |
|---|---|
| Lovable/custom doména + vlastný API subdoménový host | Nastaviť verejné VITE_API_URL; backend povolí presný frontend origin |
| Vercel na *.vercel.app | Klient vynucuje relatívne /api; rewrite /api a /healthz musí smerovať na nový Hetzner ingress |
| Lokálny Vite | /api proxy na VITE_DEV_API_PROXY alebo 127.0.0.1:8000 |
| Lovable preview a API na inej doméne | Priame credentialed CORS; preveriť cross-site cookies a Safari, nepredpokladať úspech |

`VITE_API_URL` je verejný build parameter, bez koncového `/api`.
Nastaviť ho ešte pred buildom. Súčasný `vercel.json` stále smeruje na Railway;
jeho skopírovanie do Lovable samo proxy nevytvorí.

Každá API požiadavka zachová `credentials: "include"`,
`X-Requested-With: XMLHttpRequest` a pri zvolenej organizácii `X-Organization-Id`.
Používateľská session je podpísaná HttpOnly cookie; neprepisovať ju na localStorage token,
Supabase Auth alebo vymyslený JWT. Produkčná cookie má `__Host-` prefix, Secure, Path=/ a nemá Domain.

Preferovať spoločný HTTPS site pre frontend/API alebo overenú same-origin proxy.
Cross-site potrebuje `SameSite=None` a Secure, ale Safari alebo nastavenia súkromia
môžu cookies stále zablokovať. CORS nesmie používať `*` pre credentialed požiadavky.
Podrobnosti: [ENVIRONMENT.md](ENVIRONMENT.md).

## Zachovať produktové hranice

- Povolené profily sú heartbeat a internetdb; chybový stav 409 blokovaných profilov zobraziť zrozumiteľne.
- Kvóty a role vynucuje backend. Free nemá API kľúče; nevytvárať náhradný administrátorský kľúč vo frontende.
- PoC UI nesmie tvrdiť, že prefixová kontrola príkazu vykonala exploit alebo potvrdila HTTP 200.
- SARIF/CSV exporty fungujú podľa backendovej autorizácie; nové exportné routy nie sú povolené pre API kľúče len preto, že majú reports:read.
- Stripe existuje v kóde, teraz sa neaktivuje. Produkčný chýbajúci billing config sa nesmie nahradiť úspešnou simuláciou.
- PWA nesmie offline cacheovať tenantové API dáta. Zachovať NetworkOnly pre /api a oddelenie zdravotných sond.

## Akceptácia pred publikovaním

1. Build, TypeScript a frontend testy; porovnať počet a účel existujúcich obrazoviek.
2. Login → refresh → /api/auth/me → logout; overiť Safari/iPhone aj PWA.
3. Prepnutie organizácie vyčistí relevantné query cache; nálezy a reporty patria správnemu tímu.
4. Aplikácia → overenie vlastného cieľa → povolený beh → dokončenie workerom → nález/report.
5. Neznáma/cudzia organizácia a obmedzená rola zostanú odmietnuté.
6. Blokované CLI profily, kvóta a nenastavené Stripe majú skutočný chybový stav.
7. Priamy vstup na vnorenú route aj obnovenie stránky fungujú; /api a /healthz nevracajú SPA HTML.
8. Zaznamenať frontend repo/vetvu/SHA, API a worker SHA, domény a vlastné výsledky.

Body vyššie sú plán, nie vykonané browserové testy.
