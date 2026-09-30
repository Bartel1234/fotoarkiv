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
7. Log ind, og tryk derefter **Start backup** på kontoen i portalen. Portalen afslutter login-browseren automatisk, før synkroniseringen begynder. Du kan også bruge **Afslut login** på kontokortet. Hver konto har sin egen daglige kørselsplan omkring klokkeslættet `SYNC_HOUR`.

## Betjening

- Dashboardet viser samlet antal filer samt status, antal filer og startknapper for hver ny konto. Hovedfeltets seneste kørsel og log gælder stadig den oprindelige konto.
- `BACKUP_DIR` får filer fra Google Fotos. `APPDATA_DIR/chrome` indeholder Google-login og må ikke deles med andre.
- Hvis login udløber, åbn **Google-login** for netop den konto igen. Synkroniseringen genoptages normalt fra dens gemte position.
- Login-containeren har ingen åben port på Unraid og nås gennem portalen. Udgiv ikke port 8787 direkte på internettet; brug dit LAN eller VPN.
- Hvis browseren ikke åbner, kan opstartsfejlen ses i `APPDATA_DIR/control/login-browser.log` og med `docker compose logs login`. Login-visningen bruger stadig fjernvisning af browseren internt; Google-login kan ikke flyttes til den almindelige browser på din pc og samtidig genbruges direkte af synkroniseringsmotoren.
- Første download af et stort bibliotek kan tage dage. Den aktuelle kørselslog findes også i `APPDATA_DIR/control/activity.log`.

## Begrænsninger

Google tilbyder ikke en officiel API til denne type komplet, automatisk backup. Værktøjet styrer derfor webinterfacet og kan holde op med at virke, hvis Google ændrer login eller siden. Der er ingen garanti for, at det virker med din konto, før første synkronisering er afprøvet.

`gphotos-cdp` synkroniserer hovedbiblioteket. Filer, som kun findes i Arkiv eller i delte albums og ikke i hovedbiblioteket, bliver endnu ikke downloadet. Albumindekseringen læser også deres metadata, men albummapper indeholder kun de filer, der er hentet lokalt. Det sletter ikke fra Google Fotos. Sørg for en separat backup af Unraid-mappen og kontrollér konkrete billeder/videoer efter første kørsel.

Kørselsplanen er daglig og forsøger igen efter fejl. Ændring af `SYNC_HOUR` kræver genstart af `sync`-containeren og får virkning efter næste kørsel. Flere konti kan synkronisere samtidig og bruge betydelig CPU, disk og netværk.

## Fuld gennemgang ved ufuldstændigt arkiv

Hvis antallet af hentede filer er meget lavere end i Google Fotos, skal du vælge **Gennemgå hele arkivet** ud for kontoen. Den eksisterende downloadposition gemmes i `APPDATA_DIR/control/accounts/<mail>/lastdone-before-rescan` (for den gamle konto i `APPDATA_DIR/control`), og gennemgangen starter forfra fra tidslinjens ældste del. Allerede hentede billedfiler slettes ikke. Nogle af dem kan blive hentet igen og erstattet. Første fulde gennemgang af et stort arkiv kan tage lang tid og kræver ledig plads. Undgå at starte Google-login for samme konto under kørsel.

Syncmotoren venter nu på, at Google Fotos indlæser tidslinjen, og stopper med fejl, hvis siden ikke ruller. En afsluttet kørsel betyder stadig kun, at værktøjet nåede det, som webinterfacet viste. Sammenlign antal og de ældste årstal med Google Fotos, før du regner kopien for komplet.

## Visning og download af lokale filer

Åbn **Se billeder og videoer** ud for kontoen i portalen på port 8787. Arkivet har sin egen side pr. konto. Vælg eventuelt et album, søg efter filnavn, blad gennem miniaturebillederne, og klik på et billede eller en video for at se den i browseren. **Hent fil** gemmer et enkelt originalt medie. Markér flere filer og vælg **Hent valgte som ZIP** for en lokal kopi. ZIP streames direkte til browseren uden en ekstra fuld ZIP-kopi på Unraid; der kan vælges højst 500 filer og 10 GB pr. download. Store biblioteker kan hentes i flere portioner.

Arkivvisningen læser kun filerne under `BACKUP_DIR` og uploader intet til Google. Browseren kan ikke vise alle billed- og videoformater; en fil kan stadig hentes med **Hent fil**. Miniaturebilleder gemmes under `APPDATA_DIR/control/thumbnails`. Portalen kræver sin adgangskode også for visning og downloads; udgiv ikke port 8787 direkte på internettet.

## Afslut login fra portalen

**Start backup** afslutter automatisk kontoens login-browser og venter på, at Chrome er lukket, før samme profil bruges til synkronisering. **Afslut login** lukker en åben session uden at starte backup. Gentagne klik på Google-login for samme åbne konto opretter ikke flere loginanmodninger. Kontoen og den gemte Google-session bevares.

## Albums, datoer og mappeorganisering

Ved backup læses Google Fotos' albumoversigt og billeddatoer gennem kontoens gemte browserprofil. Det er en uofficiel, læsende webprotokol; den ændrer ikke albums eller billeder hos Google. Protokolfelterne er undersøgt i [Google Photos Toolkit API](https://github.com/xob0t/Google-Photos-Toolkit/blob/main/src/api/api.ts) og [responsformatet](https://github.com/xob0t/Google-Photos-Toolkit/blob/main/src/api/parser.ts). Fotoarkivs implementering er selvstændig og bruger kun læsemetoderne lcxiM, Z5xsfc og snAcKc.

Lokalt får hver konto denne struktur:

- `Bibliotek/År/Måned/originalnavn--Google-id.ext`: én hovedfil pr. downloadet medie. Google-id forhindrer sammenblanding af ens filnavne.
- `Albums/Albumnavn--album-id/originalnavn--Google-id.ext`: alle lokalt hentede medlemmer af albummet. Mappenavnet bruger en kort hash af album-id for at skelne albums med samme navn.
- `.fotoarkiv/`: albumindeks, SQLite-filregister og oplysninger til at springe allerede organiserede downloads over.

Filer får ændringsdato fra Googles billeddato (ikke hentetidspunktet). År/måned og arkivets viste dato tager højde for den tidszone, som Google returnerer. EXIF-data og mediefilernes indhold ændres ikke. Serverens filoprettelsesdato kan ikke generelt sættes til Googles dato.

Eksisterende Google-id-mapper omorganiseres automatisk før og efter backup, når et komplet albumindeks er hentet. **Opdater albums og organiser filer** på kontoens billedside kan bestille omorganisering uden at hente mediefiler igen. Vent til en igangværende backup er afsluttet. Fremdriften vises i kontoens aktivitetslog.

Hardlinks bruges, hvor filsystemet tillader det. På Unraid kan filer på forskellige diske kræve en verificeret kopi; status angiver antallet af registrerede albumkopier. Albummapper kan derfor kræve ekstra plads. Nye downloads organiseres løbende efter hver fil, så der ikke ophobes en Google-id-mappe pr. billede. Statistikken tæller kun hovedfiler, ikke albumreferencer. Eksisterende albumfiler slettes ikke, hvis et album senere fjernes eller omdøbes hos Google; dette er et bevarende backuparkiv.

Migrationen gemmer filregisteret før den gamle fil fjernes, afviser symlinks og stopper ved filkonflikter. En afbrudt kørsel kan genoptages. Filer uden matchende Google-metadata bliver i deres gamle mappe og vises stadig i arkivet. Et afbrudt eller fejlet metadataindeks erstatter ikke det sidste komplette indeks. Hold en separat backup af serverens filer før store omorganiseringer.

## Opdater eksisterende installation på Unraid

Installationen fra ZIP/tar er ikke et git-checkout. Brug følgende i Unraid-terminalen. Kommandoen bevarer `.env`, appdata og downloadede medier:

```sh
(
set -e
cd /mnt/user/appdata/fotoarkiv-projekt
update_dir=$(mktemp -d)
trap 'rm -rf "$update_dir"' EXIT
curl -fL https://github.com/Bartel1234/fotoarkiv/archive/refs/heads/main.tar.gz -o "$update_dir/source.tar.gz"
tar -xzf "$update_dir/source.tar.gz" -C "$update_dir"
docker compose stop sync login
cp -a "$update_dir/fotoarkiv-main/dashboard/." ./dashboard/
cp -a "$update_dir/fotoarkiv-main/login/." ./login/
cp "$update_dir/fotoarkiv-main/worker.sh" ./worker.sh
cp "$update_dir/fotoarkiv-main/account-worker.sh" ./account-worker.sh
cp "$update_dir/fotoarkiv-main/compose.yaml" ./compose.yaml
docker compose build sync dashboard
docker compose up -d --no-deps --force-recreate sync login dashboard
)
```

Efter opdatering: genindlæs portalen og åbn kontoens billedside. Vælg **Opdater albums og organiser filer**, eller start backup. Første organisering kan tage tid, især hvis hardlinks ikke er mulige. Login kræves kun igen, hvis den gemte Google-session er udløbet.

## Afbryd en kørsel

**Afbryd backup** vises ved kontoen og på dens billedside, når en kørsel er aktiv eller bestilt. Stopanmodningen gælder kun den valgte konto og afslutter dens procesgruppe; andre konti fortsætter. Portalen viser **Afbryder…**, indtil processen er lukket. Status bliver **Afbrudt af brugeren** (exitkode 130). Hentede filer og downloadposition bevares; en delvis download kan blive hentet igen ved næste start. Den daglige kørselsplan fortsætter. En igangværende organisering kan også afbrydes og genoptages.
