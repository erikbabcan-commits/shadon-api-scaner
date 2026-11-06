# STRÁŽ — koordinovaný prechod databázy 008 → 009

Toto je postup pre release operátora, nie záznam vykonaného produkčného upgrade.
Posledný používateľom doložený Railway runtime má API commit `83a25c3`, PostgreSQL
18.6 a revíziu `008_postgres_uuid_and_audit_fk`. Kandidát v PR #6 očakáva
`009_cvss_and_poc_fields`. Pred zásahom treba znovu overiť runtime API aj workera.

## Hranica kompatibility

API pri štarte vyžaduje presný Alembic head svojho image. Starý image s head 008
po upgrade databázy na 009 nenabehne. Nový image s head 009 nenabehne na 008.
Nespoliehať sa na to, že už bežiaci starý proces po zmene schémy ešte odpovedá.
API a worker sa nasadzujú ako koordinovaná dvojica na rovnaký release commit.

Migrácia 009 pridáva štyri nullable stĺpce nálezov: `cvss_score`, `cvss_vector`,
`poc_command`, `remediation_patch`. Jej downgrade tieto stĺpce **odstráni aj s dátami**.
Príkaz `alembic downgrade 008_postgres_uuid_and_audit_fk` preto nie je automatický
produkčný rollback.

## Predpoklady

1. Presne určené a úspešne otestované nové API/worker image; zaznamenané SHA/digesty
   nových aj pôvodných image. Zelené CI sa nesmie nahradiť stavom „job sa nespustil“.
2. Čerstvá súkromná záloha zdrojového PostgreSQL 18 a úspešná obnova do novej,
   izolovanej databázy podľa [prevádzkového postupu](OPERATIONS_ACCEPTANCE.md).
   Použiť `pg_dump`/`pg_restore` klienta kompatibilného so zdrojovým serverom,
   pre aktuálny zdroj klienta 18. Záloha musí byť dostupná mimo pôvodnej služby.
3. Súkromný súpis konfigurácie, session/integračných tajomstiev a trvalých súborov.
   Zistiť rozpracované úlohy v Redise; worker najprv nechať dokončiť alebo riadene
   zastaviť. Prenos iba PostgreSQL sám nezachová rozpracovaný front.
4. Dohodnuté servisné okno, zablokované nové zápisy a integrácie, určený operátor
   a návratový cieľ. Do dôkazov patria iba časy, revízie, počty a výsledky kontrol.

## Preferovaný postup pri presune na VPS

1. Pripraviť nový súkromný Postgres, Redis a konfiguráciu na cieľovom serveri.
   Produkčný frontend zatiaľ ponechať na pôvodnom API. Nový worker ešte nespúšťať.
2. Na izolovanom cieli obnoviť skúšobnú zálohu 008 a overiť revíziu, počty,
   vzťahy a auditné ochrany. Nespúšťať notifikácie, platby ani skeny z obnovenej kópie.
3. Novým kandidátskym API image vykonať na tejto kópii `python -m app.migrations upgrade`.
   Overiť revíziu 009, štart API a zhodu modelu. Starý Railway image obsahuje iba
   svoj head; jeho `upgrade head` nemusí vedieť migrovať na 009.
4. V servisnom okne zastaviť nové zápisy a riadene odstaviť pôvodný worker/API.
   Vytvoriť finálnu zálohu. Finálny import robiť do ďalšej novej databázy, nie
   prepisovať produkčný zdroj ani používanú skúšobnú kópiu. Zopakovať kontroly a upgrade.
5. Spustiť nové API a worker rovnakého release. Overiť readiness s `ready=true`,
   autorizované login/me/logout, tenantové hranice a jednu povolenú syntetickú úlohu
   vrátane výsledku workera. Až potom prepnúť serverový upstream frontendovej proxy.
   Browser naďalej volá relatívne `/api/*` a `/healthz/*`.
6. Pôvodnú databázu a zálohu ponechať chránené počas dohodnutej retencie.
   Po prijatí nových zápisov nie je návrat na starú databázu bezstratový; treba
   najprv zachovať a vyhodnotiť aj tieto nové zápisy.

## Upgrade na pôvodnom hostingu

Ak sa nemení server, po príprave nových image a overení zálohy zastaviť zápisy,
worker aj API. Migrovať **raz** novým API image, potom spustiť nové API a worker.
Deploy cez dva nezávislé automatické reštarty bez servisného okna nie je tento postup.
Advisory lock migrácie serializuje migrátorov, ale nezastavuje staré aplikačné procesy.

## Postup pri zlyhaní

- Ak migrácia zlyhá, najprv súkromne zistiť skutočnú revíziu a stav schémy.
  PostgreSQL transakčné DDL pri skúšobnom zlyhaní 009 vrátilo revíziu aj stĺpce
  na 008. Je to test konkrétnej migrácie, nie záruka pre ľubovoľný incident.
- Ak ostala konzistentná 008 a nevznikli nové zápisy, možno obnoviť pôvodnú dvojicu
  image po overení jej kompatibility. Neopakovať migráciu naslepo.
- Ak je databáza na 009, preferovať opravu nového release so zachovaním 009.
  Staré API s head 008 proti nej nereštartovať.
- Ak je nutný návrat na starý release, uchovať aj aktuálny stav 009 a obnoviť
  prechodovú zálohu 008 do **novej izolovanej databázy**. Overiť ju s kompatibilným
  starým image a až potom koordinovane prepnúť API aj worker. Rozdiely od zálohy
  musia byť vyhodnotené; nesmú sa potichu zahodiť nové nálezy alebo účty.

## Rozsah vykonanej skúšky

`tests/test_pg_cutover_009.py` používa výhradne loopback testovací server a vytvára
vlastnú náhodne pomenovanú databázu, ktorú v `finally` odstráni. Testovací DB účet
potrebuje `CREATEDB`; test nesmie smerovať na produkciu. Overuje startup guard
s revíznymi adresármi končiacimi na 008 a 009, transakčné zlyhanie 009,
zachovanie starého nálezu a stratu nových polí pri downgrade. Nespúšťa historický image.

Samostatná lokálna skúška PostgreSQL 18 vykonala custom-format dump na 008,
posunula zdroj na 009 a obnovila dump do novej databázy na 008. Overila počty,
väzbu nálezu na aplikáciu a zachovanie immutable audit triggera. Použila iba
syntetické dáta. Dôkazy sú v [release zázname](RELEASE_READINESS_2026-11-06.md).
Tým **nie je potvrdená produkčná záloha, produkčný restore ani beh finálnych image**.
