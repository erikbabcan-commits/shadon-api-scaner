# Plánovanie a obnova doručenia

Toto opisuje kandidátsky kód, nie potvrdené produkčné nasadenie. API a worker
vyžadujú rovnaký release a schému **010_alert_outbox_leases**.

## Automatické skeny

| Efektívny plán | Automatické okno UTC |
|---|---|
| Free / expirované alebo neaktívne predplatné | Žiadne; manuálne skeny podľa kvóty |
| Starter | Kalendárny týždeň od pondelka 00:00 |
| Pro | Kalendárny deň od 00:00 |
| Agency | Kalendárna hodina od :00 |

Dispatcher kontroluje aktuálne okno každú minútu a pri štarte workera. Vytvorí
najviac jeden admission na aplikáciu/profil v danom okne; neprehráva historické
okná. Prvý vhodný tick môže prísť aj uprostred okna. Manuálny beh v tomto okne
už daný profil pokrýva. Zapnuté príznaky, dostupnosť profilu, oprávnenia, overenie
cieľov a mesačná kvóta naďalej platia. Osem CLI profilov zostáva blokovaných.

Staré nastavenia `HEARTBEAT_INTERVAL_MINUTES`, `NUCLEI_WEEKLY_CRON` a
`SUPPLY_CHAIN_WEEKLY_CRON` ostávajú parsovateľné kvôli kompatibilite konfigurácie,
ale nový dispatcher podľa nich neplánuje. Autoritatívna frekvencia je efektívny
plán vyššie; staré queued job names sa vykonajú cez rovnaké pravidlá.

PostgreSQL row lock organizácie serializuje kontrolu kvóty aj scheduler admission.
Run, spotreba kvóty a immutable audit s `trigger=scheduler` sa commitnú spolu.
Ak proces spadne pred odovzdaním do Redisu, ďalší tick publikuje rovnaké run ID
s rovnakým ARQ job ID. Nepočíta ďalšiu kvótu. Scheduler queued run čakajúci viac
ako hodinu skončí failed; už spotrebované okno/kvóta sa nevracajú na opakovanie.

Obnova sa týka výhradne queued runov s JSON auditným dôkazom scheduler ownership.
Manuálne/CI runy a running runy sa nemenia. Nie je to globálny execution mutex
pre súbežne prijaté manuálne skeny ani obnova running úlohy po páde; tie vyžadujú
samostatné execution lease/fencing a zostávajú otvorené. Vek sám neoprávňuje
zabiť alebo opakovať sken, ktorý môže stále bežať v inom workeri.

## Notification outbox

Udalosť sa ukladá v transakcii s nálezom. Worker claimne pending udalosť alebo
processing udalosť s chýbajúcim/expirovaným lease. Pri claimnutí vytvorí UUID
token a dvojminútový lease; token aj platnosť sa kontrolujú pri doručení/ack.
Starý worker nesmie potvrdiť nového vlastníka udalosti. Pred odoslaním sa znovu
kontroluje aktívny kanál, org/app scope, typ udalosti a severity politika.

- Najviac 5 claim pokusov, oneskorenia po zlyhaní 30/60/120/240 sekúnd.
- Maximálny vek 24 hodín; vyčerpané alebo už neplatné udalosti skončia failed.
- Dávka najviac 25, súbeh najviac 8, celkový timeout jedného doručenia 10 sekúnd.
- Existujúce sent/failed udalosti sa automaticky neobnovujú. `processed_at` je
  terminálny čas, nie čas dočasného vlastníctva.
- Webhook `event_id` aj `Idempotency-Key` sú stabilné ID udalosti, nie ID kanála.
  HMAC podpisuje presné odoslané bajty. Prijímateľ môže podľa ID deduplikovať.

Ide o obmedzené **at-least-once pokusy**, nie garantované ani presne jedno externé
doručenie. Pád po prijatí správy a pred DB ack môže vyvolať duplicitu s rovnakým
ID. Dočasná chyba sa obnoví; dlhý výpadok, chybná konfigurácia alebo vyčerpané
pokusy vyžadujú pozornosť operátora. Žiadny test sám nepotvrdzuje produkčné alerty.

Regresie používajú skutočné PG row locks/SKIP LOCKED a stale fencing. Samostatný
lokálny TLS receiver overuje 503 → retry → 200, presné HMAC a ID pri zapnutej
verifikácii certifikátu. Fixture DNS je obmedzené iba na vlastný loopback server;
žiadna testovacia správa sa neposiela externému príjemcovi.
