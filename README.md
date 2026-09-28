# Fotoarkiv Backup til Unraid

> Status: Projektet er testet lokalt for webinterface og styring. En fuld download fra Google Fotos er endnu ikke verificeret på en Unraid-server med en rigtig konto.

Et lokalt webinterface til automatisk download fra Google Fotos. Synkroniseringen bruger [gphotos-cdp](https://github.com/perkeep/gphotos-cdp) via [Jake Whartons Docker-image](https://github.com/JakeWharton/docker-gphotos-sync). Det styrer Google Fotos i Chromium, gemmer den sidst hentede post og fortsætter inkrementelt. Ingen Google Takeout er nødvendig.

Dashboardet viser live status, workerens tilgængelighed, antal filer, diskforbrug, seneste filer, næste kørsel og log. Det opdateres automatisk hvert 8. sekund.

## Opdatering fra forrige udgave

Pak filerne oven i den eksisterende projektmappe. Behold din `.env`, `APPDATA_DIR` og `BACKUP_DIR`. Kør derefter `docker compose up -d --build`. Billeder og gemt Google-login ligger i mapperne fra `.env` og berøres ikke af opdateringen.

## Installation

Unraid kræver et Docker Compose-plugin, hvis `docker compose version` ikke allerede virker i terminalen.

1. Pak projektet ud på Unraid, eksempelvis i `/mnt/user/appdata/fotoarkiv-projekt`.
2. Kopiér `.env.example` til `.env`. Ret `APPDATA_DIR`, `BACKUP_DIR` og vælg en stærk `APP_PASSWORD`. Sørg for, at `BACKUP_DIR` ligger på et share med tilstrækkelig plads.
3. Kør fra projektmappen:

   ```sh
   docker compose up -d --build
   ```

4. Åbn `http://DIN-UNRAID-IP:8787`. Brug et vilkårligt brugernavn og adgangskoden fra `.env`.
5. Tryk **Åbn Google-login** under **Google-login** i portalen. Skrivebordet vises på samme adresse og beskyttes af portalens adgangskode. Chrome åbner Google Fotos automatisk. Giv den lidt tid første gang.
6. Log ind på din egen Google-konto, og **luk Chrome-vinduet helt**.
7. Tryk **Start synkronisering nu** på dashboardet. Efterfølgende kører den dagligt omkring klokkeslættet `SYNC_HOUR` fra `.env`.

## Betjening

- Status, antal filer, diskforbrug og seneste 100 loglinjer vises på dashboardet.
- `BACKUP_DIR` får filer fra Google Fotos. `APPDATA_DIR/chrome` indeholder Google-login og må ikke deles med andre.
- Hvis login udløber, åbn **Google-login** igen. Synkroniseringen genoptages normalt fra gemt position.
- Login-containeren har ingen åben port på Unraid og nås gennem portalen. Udgiv ikke port 8787 direkte på internettet; brug dit LAN eller VPN.
- Første download af et stort bibliotek kan tage dage. Den aktuelle kørselslog findes også i `APPDATA_DIR/control/activity.log`.

## Begrænsninger

Google tilbyder ikke en officiel API til denne type komplet, automatisk backup. Værktøjet styrer derfor webinterfacet og kan holde op med at virke, hvis Google ændrer login eller siden. Der er ingen garanti for, at det virker med din konto, før første synkronisering er afprøvet.

`gphotos-cdp` synkroniserer hovedbiblioteket. Fotos, som kun findes i Arkiv, og albumstruktur er ikke understøttet. Det sletter ikke fra Google Fotos. Sørg for en separat backup af Unraid-mappen og kontrollér konkrete billeder/videoer efter første kørsel.

Kørselsplanen er daglig og forsøger igen efter fejl. Ændring af `SYNC_HOUR` kræver genstart af `sync`-containeren og får virkning efter næste kørsel.
