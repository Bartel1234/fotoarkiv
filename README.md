# Fotoarkiv Backup til Unraid

> Status: Projektet er testet lokalt for webinterface og styring. En fuld download fra Google Fotos er endnu ikke verificeret på en Unraid-server med en rigtig konto.

Et lokalt webinterface til automatisk download fra Google Fotos. Synkroniseringen bruger [gphotos-cdp](https://github.com/perkeep/gphotos-cdp) via [Jake Whartons Docker-image](https://github.com/JakeWharton/docker-gphotos-sync). Det styrer Google Fotos i Chromium, gemmer den sidst hentede post og fortsætter inkrementelt. Ingen Google Takeout er nødvendig. Flere konti kan tilføjes i portalen. Hver konto får sin egen browserprofil, downloadposition og undermappe under `BACKUP_DIR`.

Dashboardet viser live status, workerens tilgængelighed, antal filer, diskforbrug, seneste filer, næste kørsel og log. Det opdateres automatisk hvert 8. sekund.

## Opdatering fra forrige udgave

Pak filerne oven i den eksisterende projektmappe. Behold din `.env`, `APPDATA_DIR` og `BACKUP_DIR`. Kør derefter `docker compose up -d --build`. Den tidligere konto vises som **Eksisterende konto** og beholder sin profil og sine filer direkte i hovedmappen. Nye konti får mapper navngivet efter mailadressen, eksempelvis `BACKUP_DIR/bruger@example.com`. Eksisterende billeder flyttes ikke automatisk. Tilføj ikke den tidligere konto igen med dens mailadresse, medmindre du ønsker en ny, separat download fra begyndelsen.

## Installation

Unraid kræver et Docker Compose-plugin, hvis `docker compose version` ikke allerede virker i terminalen.

1. Pak projektet ud på Unraid, eksempelvis i `/mnt/user/appdata/fotoarkiv-projekt`.
2. Kopiér `.env.example` til `.env`. Ret `APPDATA_DIR`, `BACKUP_DIR` og vælg en stærk `APP_PASSWORD`. Sørg for, at `BACKUP_DIR` ligger på et share med tilstrækkelig plads.
3. Kør fra projektmappen:

   ```sh
   docker compose up -d --build
   ```

4. Åbn `http://DIN-UNRAID-IP:8787`. Brug et vilkårligt brugernavn og adgangskoden fra `.env`.
5. Under **Google Fotos-konti**, skriv mailadressen og tryk **Tilføj konto**. Mappen oprettes under `BACKUP_DIR`.
6. Tryk **Google-login** på den ønskede konto. Et popup-vindue åbner på samme adresse og beskyttes af portalens adgangskode. Chrome starter automatisk og fylder visningen med Google Fotos for den valgte konto; du skal ikke åbne en terminal. Giv browseren lidt tid første gang. Hvis popup-vinduet blokeres, åbnes login i den aktuelle fane.
7. Log ind, **luk Chrome i login-skrivebordet**, og luk popup-vinduet. Tryk derefter **Start backup** på kontoen. Hver konto har sin egen daglige kørselsplan omkring klokkeslættet `SYNC_HOUR`.

## Betjening

- Dashboardet viser samlet antal filer samt status, antal filer og startknapper for hver ny konto. Hovedfeltets seneste kørsel og log gælder stadig den oprindelige konto.
- `BACKUP_DIR` får filer fra Google Fotos. `APPDATA_DIR/chrome` indeholder Google-login og må ikke deles med andre.
- Hvis login udløber, åbn **Google-login** for netop den konto igen. Synkroniseringen genoptages normalt fra dens gemte position.
- Login-containeren har ingen åben port på Unraid og nås gennem portalen. Udgiv ikke port 8787 direkte på internettet; brug dit LAN eller VPN.
- Hvis browseren ikke åbner, kan opstartsfejlen ses i `APPDATA_DIR/control/login-browser.log` og med `docker compose logs login`. Login-visningen bruger stadig fjernvisning af browseren internt; Google-login kan ikke flyttes til den almindelige browser på din pc og samtidig genbruges direkte af synkroniseringsmotoren.
- Første download af et stort bibliotek kan tage dage. Den aktuelle kørselslog findes også i `APPDATA_DIR/control/activity.log`.

## Begrænsninger

Google tilbyder ikke en officiel API til denne type komplet, automatisk backup. Værktøjet styrer derfor webinterfacet og kan holde op med at virke, hvis Google ændrer login eller siden. Der er ingen garanti for, at det virker med din konto, før første synkronisering er afprøvet.

`gphotos-cdp` synkroniserer hovedbiblioteket. Fotos, som kun findes i Arkiv, og albumstruktur er ikke understøttet. Det sletter ikke fra Google Fotos. Sørg for en separat backup af Unraid-mappen og kontrollér konkrete billeder/videoer efter første kørsel.

Kørselsplanen er daglig og forsøger igen efter fejl. Ændring af `SYNC_HOUR` kræver genstart af `sync`-containeren og får virkning efter næste kørsel. Flere konti kan synkronisere samtidig og bruge betydelig CPU, disk og netværk.

## Fuld gennemgang ved ufuldstændigt arkiv

Hvis antallet af hentede filer er meget lavere end i Google Fotos, skal du vælge **Gennemgå hele arkivet** ud for kontoen. Den eksisterende downloadposition gemmes i `APPDATA_DIR/control/accounts/<mail>/lastdone-before-rescan` (for den gamle konto i `APPDATA_DIR/control`), og gennemgangen starter forfra fra tidslinjens ældste del. Allerede hentede billedfiler slettes ikke. Nogle af dem kan blive hentet igen og erstattet. Første fulde gennemgang af et stort arkiv kan tage lang tid og kræver ledig plads. Undgå at starte Google-login for samme konto under kørsel.

Syncmotoren venter nu på, at Google Fotos indlæser tidslinjen, og stopper med fejl, hvis siden ikke ruller. En afsluttet kørsel betyder stadig kun, at værktøjet nåede det, som webinterfacet viste. Sammenlign antal og de ældste årstal med Google Fotos, før du regner kopien for komplet.
