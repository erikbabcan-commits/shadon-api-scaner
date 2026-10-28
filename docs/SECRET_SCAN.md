# Secret gate a historický incident

CI používa Gitleaks 8.30.1, oficiálny Linux x64 archív overený pripnutým SHA-256.
Job `secret-scan` blokuje backend aj frontend jobs na PR do main/master a na push
do main/master/develop. Vyžadované status checks na GitHube musí vynútiť vlastník
repozitára; ich aktuálne nastavenie toto PR nemení ani nepotvrdzuje.

Kontroly: celý pracovný strom, zakázané sledované credential/DB súbory a všetky
commity zavedené PR/pushom. Commit rozsah pochádza z GitHub eventu a vyžaduje plné
SHA. Nový secret aj v neskôr odstránenom commite rozsah zablokuje. Žiadny plošný
baseline, ignore súbor ani `gitleaks:allow` komentár sa nepoužíva na potlačenie nálezov.

Historické incidenty zo starého main nie sú automaticky schválené tým, že prejde
kontrola nových commitov. Úplný scan histórie zostáva samostatnou incidentnou kontrolou
a bude vracať nenulový exit, pokým história obsahuje známe nálezy. Neprepisovať ju
len kvôli zelenému CI; najprv rotovať a prípadný rewrite výslovne schváliť.

## Lokálny hook

Nainštalovať overený Gitleaks 8.30.1 podľa oficiálneho release a sprístupniť `gitleaks`
v PATH. Potom v tomto klone zapnúť hook (iba lokálna Git konfigurácia):

```sh
git config --local core.hooksPath .githooks
python3 scripts/test_secret_gate.py
python3 scripts/check_secrets.py tree
python3 scripts/check_secrets.py history
```

Hook kontroluje index, nie iba pracovné súbory. Nepovolí nútene pridané .env, privátne
kľúče, lokálne DB ani backup artefakty. `.env.example` je iba sanitizovaná šablóna,
nie výnimka z obsahového secret scanu. Aktívne lokálne .env patria mimo Git.
Chýbajúci scanner alebo neplatný report je chyba, nie úspech.

`scripts/test_secret_gate.py` vytvára dočasné lokálne Git repozitáre, syntetické
náhodné tajomstvo a overuje exit 1 aj neprítomnosť jeho hodnoty vo výstupe.
Nikdy sa nepripája k aplikácii, databáze alebo externému cieľu.
Výstup obsahuje iba RuleID, názov súboru, riadok a commit, nie Match/Secret/autor.
