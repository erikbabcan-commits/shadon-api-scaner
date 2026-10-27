# STRÁŽ — pripravená rotácia kompromitovaných tajomstiev

Stav: **pripravené, nevykonané**. Vyžaduje výslovné schválenie produkčného zásahu.
Nálezy v historickom NOTION_NOTES.md sa považujú za kompromitované nezávisle od toho,
či ešte zodpovedajú produkcii. Zmazanie zo stromu, .gitignore ani zelené CI nie sú rotácia.

## Cieľ a prístup

Railway workspace `2b4de623-f58a-4f86-9123-fa90190c7224`, projekt `dev-new`
`f233a228-5a2a-49b3-9be5-2cafedcb7049`, environment `production`
`ba5166f1-65be-4244-899c-f27080570e5f`. Pred zásahom tieto identity overiť.
Služby: Postgres, Redis, straz-api, straz-worker; názvy/verzie sú podklady, nie dôkaz
aktuálneho runtime. Bez oprávneného Railway prístupu je vykonanie blokované.

Nové hodnoty vytvárať priamo cez provider secret generátor alebo bezpečný skrytý vstup.
Ak služba podporuje Railway výraz `${{secret(64)}}`, použiť ho bez čítania výsledku;
pred uložením overiť podporu na danom type premennej. Nepísať hodnoty do CLI argumentov,
shell histórie, GitHubu, chatu, screenshotov ani artefaktov. Nikdy nepoužiť `set -x`,
`env`, výpis všetkých premenných ani výpis celej provider odpovede.

## Schvaľovaný konkrétny rozsah

1. Potvrdiť čerstvú súkromnú zálohu a úspešný izolovaný restore podľa
   [prevádzkového postupu](OPERATIONS_ACCEPTANCE.md). Zaznamenať iba ID, čas a výsledok.
2. Inventarizovať konzumentov DB a Redisu: API, worker, migrácie, zálohy a ďalšie
   integrácie. Overiť referenčné premenné a možnosť koordinovaného reštartu.
3. Schváliť krátke maintenance okno. Pozastaviť príjem nových behov a nechať dobehnúť
   aktuálne úlohy; audit ani frontu nemať za spotrebný testovací materiál.
4. **Postgres:** resetnúť credential existujúcej DB roly podporovaným provider postupom,
   zachovať databázu aj volume a aktualizovať konzumentov cez referencie. Zmena samotného
   POSTGRES_PASSWORD v prostredí existujúceho inicializovaného volume spravidla nemení
   heslo databázovej roly. Nepristupovať k tomu ako k hotovej rotácii bez DB overenia.
5. **Redis:** overiť aktuálny auth mechanizmus (ACL/requirepass), použiť jeho podporovaný
   reset a zosúladiť REDIS_URL/referencie API a workera. Zmena iba environment hodnoty
   nie je dôkaz zmeny serverového hesla. Zachovať volume, queue dáta a ACL minimum práv.
6. **Administrátor:** zmeniť heslo existujúceho používateľa cez podporovaný change-password
   tok alebo schválený runtime ORM postup (Argon2 hash a zvýšenie token_version v jednej
   transakcii). Samotná zmena STRAZ_ADMIN_PASSWORD nemení už existujúci DB účet:
   bootstrap existujúce heslo zámerne neprepisuje. Zosúladiť bootstrap premennú bezpečnou
   referenciou; nepovažovať ju za mechanizmus resetu používateľa.
7. **Session:** nahradiť STRAZ_SESSION_SECRET a koordinovane nasadiť všetky API inštancie,
   ktoré overujú tokeny. Starý podpisovací secret neuchovávať ako fallback. Worker
   zosúladiť s konfiguráciou; overiť dokončenie reštartov, nie len uloženie premenných.
8. Overiť DB SELECT 1, Redis PING, API liveness/readiness, schému a worker. Až po
   stabilizácii obnoviť príjem úloh a schválené plánovanie.

## Akceptačný dôkaz po schválení

- Služby API aj worker majú stabilný úspešný deployment; logy iba sanitizovane.
- Liveness/readiness HTTP 200, databáza aj Redis ok; staré credentials neautentifikujú.
  Overovať iba jedno kontrolované spojenie, bez výpisu credential alebo connection stringu.
- Prihlásenie admina novým heslom funguje a staré heslo nefunguje.
- Jedna vopred bezpečne zachytená stará syntetická relácia na GET /api/auth/me vracia 401
  po ukončení všetkých starých API inštancií; nová relácia funguje. Session/cookies iba
  v pamäti alebo chránenom dočasnom súbore, po overení odstrániť, nepublikovať.
- Potvrdenie rovnakého správania cez Vercel proxy. Produkčný login vytvára audit,
  preto tieto kroky nepatria do read-only kontroly pred schválením.
- Zaznamenať čas rotácie, identity služieb, nasadené SHA a výsledky bez hodnôt.

Lokálny regresný test potvrdzuje, že token podpísaný predchádzajúcim secretom zlyhá
s novým secretom. Nie je to potvrdenie vykonanej produkčnej rotácie.

## Zlyhanie a obnova

Pri strate spojenia nevymazávať DB ani volume a nespúšťať migrácie na náhodnej URL.
Overiť konzumentov a referencie v maintenance okne. Návrat k publikovaným credential
znamená opätovné otvorenie incidentu; uprednostniť opravu novej konfigurácie. Prípadný
rollback konfigurácie musí schváliť zodpovedný operátor. Overiť aj staré API repliky.

## Voliteľný prepis histórie

Nie je vykonaný ani automaticky schválený. Po rotácii možno v oddelenom mirror klone
pripraviť git filter-repo, koordinovať všetky vetvy/tagy/PR a ďalšie klony a po výslovnom
schválení publikovať prepísané refy. Žiadny force push nepatrí do tohto PR. Odstránenie
z forkov, cache a už stiahnutých kópií nemožno garantovať. Rotácia zostáva povinná.
