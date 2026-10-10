# Installation: Pangolin Manager 0.1.0-beta.3

Dette er en testudgave til **Unraid 7.x**. Panelet er installeret på DeathStar;
containerforbindelsen i denne rettelse skal stadig kontrolleres på serveren.

## 1. Installér pluginet

1. Åbn **Plugins → Install Plugin** i Unraid.
2. Indsæt denne adresse i URL-feltet:

   ```text
   https://raw.githubusercontent.com/Bartel1234/fotoarkiv/main/unraid-plugins/pangolin-manager/pangolin-manager.plg
   ```

3. Tryk **Install**. Ingen genstart af Unraid eller Newt er nødvendig.
4. Åbn **Tools → Pangolin Manager**.

Unraid henter manifestet fra GitHub. Det indeholder hele programmet med en SHA-256-
kontrolsum og downloader ingen yderligere runtime-afhængigheder. Indstillinger
bevares ved opdateringer. Brug **Plugins → Check for Updates** til senere versioner.

### Opdater fra beta.2

Åbn **Plugins → Installed Plugins → Check for Updates**, og vælg **Update** ved
Pangolin Manager. Den nye pluginversion er `2026.10.10.2` (beta.3). Genindlæs derefter
**Tools → Pangolin Manager → Indstillinger**, og vælg Newt-containeren.
Hvis containerlisten fortsat fejler, viser panelet nu en konkret fejlbesked.

**Alternativ: lokal installation**

Pak ZIP-filen ud, og kopiér `pangolin-manager.plg` til `/boot/config/plugins/`.
Vælg denne fil i den samme Install Plugin-menu. Hvis flash allerede er tilgængelig
via SMB, er stien typisk `\\DeathStar\flash\config\plugins\`.

## 2. Vælg din Newt-container

1. Åbn **Tools → Pangolin Manager → Indstillinger**.
2. Vælg din eksisterende Newt-container. Sandsynlige Newt-containere vises øverst.
3. Pangolin-adressen kan stå tom, hvis containeren har `PANGOLIN_ENDPOINT`.
4. Klik **Gem indstillinger**. Panelet kører en kontrol.

Containeren kan være grøn, mens tunnellen er gul/ukendt. Det er korrekt:
en kørende container er ikke i sig selv bevis på en fungerende tunnel.

## 3. Aktivér måling af tunnellen

**Mulighed A – Newts forbindelsesfil**

Hvis Newt allerede er konfigureret med `HEALTH_FILE`, registrerer pluginet den.
Ellers kan du redigere Newt-containeren i Unraid og tilføje en miljøvariabel:

| Felt | Værdi |
| --- | --- |
| Config Type | Variable |
| Name | Health file |
| Key | `HEALTH_FILE` |
| Value | `/tmp/healthy` |

Anvend ændringen. Det genopretter normalt containeren og afbryder tunnellen kortvarigt.
Newt opretter/fjerner filen efter forbindelsesstatus. Den skal **ikke** oprettes manuelt.
Lad pluginets Healthcheck-fil-felt være tomt for automatisk at bruge miljøvariablen.

Kontrollen bruger `test -f` i containeren. Hvis dit image ikke indeholder den kommando,
vises ukendt status; brug API-muligheden nedenfor. Understøttelse af `HEALTH_FILE`
skal kontrolleres for din konkrete Newt-version.

**Mulighed B – Pangolins API**

1. Aktivér integrations-API'et på din Pangolin-server, hvis det ikke allerede er aktivt.
2. Opret en organisationsnøgle med rettighed til at læse sites. Ingen root-nøgle er nødvendig.
3. Udfyld API-baseadresse med `/v1`, organisation-ID, site-ID og API-nøgle i pluginet.
4. Gem og test. HTTPS med et gyldigt certifikat er påkrævet til API-nøglen.

Eksempel på API-baseadresse: `https://api.dit-domæne.dk/v1`.
Newts login-secret er **ikke** en Pangolin API-nøgle. Brug det site-ID, API'et returnerer;
det er ikke nødvendigvis det samme som Newts connector-ID.

Pluginet bruger API'et, når lokal tunnelstatus er ukendt. API-ruter og felter varierer
med Pangolin-versionen. Ikke-genkendte svar vises som ukendt, ikke som forbundet.

## 4. Tilføj lokale tjenester

Tilføj navn, lokal URL og eventuelt et offentligt link. Brug dine faktiske adresser.

| Eksempel | Lokal URL (eksempel) | Kontroltype |
| --- | --- | --- |
| PhotoHarbor | `http://192.168.1.10:8787` | HTTP-sundhed |
| Home Assistant | `http://192.168.1.10:8123` | HTTP-sundhed |
| Tjeneste med adgangskrav | `https://192.168.1.10:8443` | Server svarer |

Disse IP-adresser og porte er eksempler. Kontrollen køres fra **Unraid**, og et grønt
resultat betyder ikke, at tjenesten kan nås fra internettet eller Newts Docker-netværk.
401/403 er ukendt sundhed i HTTP-sundhedstilstand, men tæller som et svar i
Server svarer-tilstand. Selvsignerede/ugyldige certifikater giver TLS-fejl.

## 5. Find widgetten på forsiden

Åbn **Dashboard** og genindlæs siden. Widgetten hedder **Pangolin / Newt** og bruger
Unraids almindelige flisesystem. Hvis den er skjult, lås Dashboard-layoutet op og
aktivér den i indholds-/widgetvælgeren.

Widgetten viser container, tunnel, antal lokale tjenester der svarer, fejltekst og
tidspunkt for sidste kontrol. Knapper: Åbn panel, Test og Pangolin.

## 6. Notifikationer og genstart

Notifikationer er fravalgt fra starten. Tilvælg dem under Indstillinger for besked ved
fejl i mindst to minutter og ved bekræftet genoprettelse. Levering styres af din
eksisterende Unraid-opsætning. Ukendt tunnelstatus giver ikke fejlalarm, men kan forhindre
en bekræftet genoprettelse. Pluginet genstarter aldrig noget automatisk.

Genstart Newt fra Overblik. Du skal bekræfte genstarten i en dialog. Brug helst lokal
adgang til Unraid, da din fjernforbindelse kan blive afbrudt.

## Afinstallation

Brug **Plugins → Pangolin Manager → Remove**. Pluginets brugerflade og baggrundskontrol
fjernes. Newt, Pangolin og dine tjenester bevares, ligesom pluginets indstillinger.

## Hvis noget ikke virker

- **Ingen Docker-liste:** kontrollér Settings → Docker.
- **Tunnel ukendt:** kontrollér healthcheck/API som beskrevet ovenfor.
- **Forældet måling:** klik Test. Hvis status igen bliver gammel, kontrollér pluginets cron-job.
- **API 401/403:** kontrollér nøgle og rettigheder.
- **API-format ukendt:** din Pangolin-version kræver muligvis en justeret adapter.
- **Log:** Newt-log-fanen viser seneste linjer med kendte secrets skjult. Gennemgå før deling.

Den valgfri API-nøgle gemmes i pluginets indstillinger på Unraids flash. Den er ikke
krypteret og må ikke komme med i offentlige backupfiler eller et GitHub-repository.
