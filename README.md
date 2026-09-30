# Fotoarkiv Backup for Unraid

A local web portal for automatic Google Photos backups, with separate accounts, album folders, a media browser and ZIP downloads. The interface defaults to **English**. Use the **🇬🇧 EN / 🇩🇰 DA** buttons at the top of the dashboard or media browser to switch to Danish. The preference is remembered in your browser. Album names, filenames and raw worker logs retain their original language.

Fotoarkiv uses [gphotos-cdp](https://github.com/perkeep/gphotos-cdp), based on [Jake Wharton's Docker image](https://github.com/JakeWharton/docker-gphotos-sync), to operate Google Photos through Chrome. No Google Takeout export is required. Each account has its own browser profile, download position and subfolder under `BACKUP_DIR`.

> Validation: the dashboard, account controls, file organization and media APIs have been tested locally. A complete Google Photos download has not been independently verified against a real account on Unraid. Check the resulting files and counts before treating the archive as complete.

## Installation

Install a Docker Compose plugin on Unraid if `docker compose version` does not work.

1. Extract the project into `/mnt/user/appdata/fotoarkiv-projekt`.
2. Copy `.env.example` to `.env`. Set `APPDATA_DIR`, `BACKUP_DIR` and a strong `APP_PASSWORD` with at least 12 characters. Choose a backup share with sufficient free space.
3. Run from the project folder:

   ```sh
   docker compose up -d --build
   ```

4. Open `http://YOUR-UNRAID-IP:8787`. Use any username and the password from `.env`.
5. Under **Google Photos accounts**, enter an email address and select **Add account**. Its folder is created under `BACKUP_DIR`.
6. Select **Google sign-in** for the account. A password-protected popup opens the browser on Unraid. Chrome opens Google Photos automatically; no terminal is needed for sign-in. Allow extra time on the first launch. If popups are blocked, sign-in opens in the current tab.
7. Sign in, then select **Start backup** in the portal. The sign-in browser closes automatically before the sync worker uses the same profile. **Close sign-in** closes it without starting a backup. Each account has a daily schedule around `SYNC_HOUR`.

## Accounts and operation

- The status panel and account cards follow the current stage: preparation, closing sign-in, indexing photos/albums, organizing files, downloading media and stopping. During Google indexing, the panel shows the latest indexed photo and album counts rather than an estimated percentage.
- The dashboard refreshes every eight seconds and shows worker availability, file counts, storage usage, recent files, schedules and activity. Select an account card to view its status and log.
- The **Existing account** keeps its original profile and files in the main backup folder. Additional accounts use folders such as `BACKUP_DIR/user@example.com`. Only add the original account again if you want a separate download starting from the beginning.
- `APPDATA_DIR/chrome` and the account browser profiles contain Google sign-in credentials. Keep them private.
- If a Google session expires, select **Google sign-in** for that account again. Sync normally resumes from its saved position.
- The sign-in container has no exposed Unraid port. Access it through the portal. Keep port 8787 on your LAN or VPN.
- Browser startup errors appear in `APPDATA_DIR/control/login-browser.log` and `docker compose logs login`. The sign-in popup uses remote browser display internally; signing in through your PC's ordinary browser does not directly provide a session to the sync worker.
- Repeated sign-in requests for an already open account do not queue additional browser launches. Starting backup requests closure and waits for Chrome to release the profile.
- The first download of a large library can take days. Logs are also stored under `APPDATA_DIR/control/accounts/<email>/activity.log`; the original account uses `APPDATA_DIR/control/activity.log`.
- The daily schedule retries after failures. Changing `SYNC_HOUR` requires restarting `sync` and takes effect after the next run. Multiple accounts can run concurrently and use substantial CPU, disk and network resources.

The downloader processes the main Google Photos library. Media that exists only in Archive or in shared albums outside the main library is not downloaded yet. Album indexing can discover its metadata, but local album folders contain only downloaded media. Fotoarkiv does not delete anything from Google Photos. Maintain a separate backup of the Unraid folder.

## Scan an incomplete archive

Select **Scan the entire archive** for an account when the local file count is much lower than in Google Photos. The previous position is saved as `APPDATA_DIR/control/accounts/<email>/lastdone-before-rescan` (under `APPDATA_DIR/control` for the original account), and scanning restarts from the oldest part of the timeline.

Existing downloaded files are preserved. Some may be downloaded again and replaced. A full scan can take a long time and requires free space. Avoid opening Google sign-in for the same account while it is running.

The worker waits for the timeline to load and reports an error if navigation stops progressing. A successful exit means it reached the content shown by the web interface; it does not prove completeness. Compare file counts and the oldest years against Google Photos.

## Browse photos, videos and albums

Select **View photos and videos** on an account card. Each account has a separate media page. Choose an album, search filenames, browse thumbnail pages and open photos or videos in the browser. **Download file** downloads an original. Select multiple files and choose **Download selected as ZIP** for a local export.

ZIP downloads stream directly to the browser without creating a second complete ZIP on Unraid. Each ZIP is limited to 500 files and 10 GB; larger libraries can be exported in portions. The archive browser reads only local files and uploads nothing to Google. Some media formats cannot be previewed but can still be downloaded. Thumbnails are cached under `APPDATA_DIR/control/thumbnails`. Viewing and downloading require the portal password.

The gallery uses a separate SQLite read index per account under `APPDATA_DIR/control/archive-index`. The first visit builds it; subsequent album switches query only the selected album and page. Catalog changes are checked at least 30 seconds apart, and a full refresh is scheduled on the next visit after five minutes. Refreshes run in the background while the previous complete index remains available. The index is rebuildable and does not modify original media.

## Albums, dates and folder organization

Backup reads Google Photos album membership and photo dates through the saved browser profile. This uses an unofficial read-only web protocol. It does not modify albums or photos in Google. Protocol fields were checked against [Google Photos Toolkit API](https://github.com/xob0t/Google-Photos-Toolkit/blob/main/src/api/api.ts) and its [response parser](https://github.com/xob0t/Google-Photos-Toolkit/blob/main/src/api/parser.ts). Fotoarkiv's implementation is independent and uses only the read methods lcxiM, Z5xsfc and snAcKc.

Each account uses this on-disk layout. Folder names are preserved when changing the interface language:

- `Bibliotek/YYYY/MM/original-name--Google-id.ext`: one primary file per downloaded item. The Google ID prevents collisions between identical filenames.
- `Albums/album-title--album-hash/original-name--Google-id.ext`: locally downloaded members of each album. A short hash distinguishes albums with identical titles.
- `.fotoarkiv/`: album metadata, the authoritative SQLite file catalog and records used to skip already organized downloads.

File modification times use Google's photo timestamp. Year/month folders and displayed Google dates account for Google's timezone offset. EXIF data and media contents are unchanged. Filesystem creation times generally cannot be set to the Google timestamp.

Existing Google-ID folders are organized before and after backup once a complete metadata index is available. **Refresh albums and organize files** on the media page requests organization without downloading media again. Wait for an active backup to finish. Progress appears in the account activity log.

Album files use hard links where supported. Files on different Unraid disks may require verified copies and additional storage. The organization report shows registered album copies. New downloads are organized individually to avoid one folder per photo. Dashboard counts include primary files rather than album references. Existing album files are retained when an album is deleted or renamed in Google Photos.

Organization saves the catalog before removing the old file, rejects symlinks and stops on file conflicts. Interrupted runs can resume. Files without matching Google metadata remain in their original folders and are still shown. Failed or interrupted metadata indexing preserves the previous complete index. Keep a separate backup before large reorganizations.

## Stop a backup

**Stop backup** appears on the account card and its media page while a run is active or pending. It stops the selected account's process group and clears pending requests. Other accounts continue running.

## Update an existing Unraid installation

An installation extracted from ZIP/tar is not a Git checkout. Run this in the Unraid terminal. It preserves `.env`, appdata and downloaded media:

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

After updating, refresh the portal and open the account's media page. Select **Refresh albums and organize files**, or start backup. Initial organization can take time, especially when hard links are unavailable. Sign in again only if the saved Google session has expired.

For dashboard-only updates, copy the new `dashboard/` directory and rebuild/recreate only `dashboard`; the sync and sign-in containers can continue running.
