# Fasteignir.is listing monitor

A small personal monitor for this saved search:

- Postcodes: **101 and 107**
- Size: **70–1000 m²**
- Price: **65,000,000–80,000,000 ISK**
- Bedrooms: **2–10**
- Bathrooms: **1–10**
- Listing type: **for sale**

The workflow runs on GitHub-hosted machines at approximately **08:07, 13:07 and 19:07 Iceland time** every day. Your own computer can be off. The seven-minute offset avoids the busiest exact-hour period for scheduled GitHub Actions.

## What it stores

`data/listings.csv` is the permanent database. It records address, postcode, price, size, rooms, bedrooms, bathrooms, property type, open-house information, dates, URL, first/last seen timestamps, status and detected changes.

`data/latest_changes.json` contains only changes from the latest successful scan.

The scraper uses the site's JSON search endpoint rather than clicking through the web interface. Because this is an unofficial endpoint, the site can change it. When parsing fails, the Action fails visibly instead of silently replacing the database.

## Set up on GitHub

1. Create a **private** GitHub repository.
2. Upload the contents of this folder, preserving `.github/workflows/scan-listings.yml`.
3. Commit and push to the repository's default branch.
4. Open **Actions → Scan house listings → Run workflow** for the first test.
5. Open the completed run and check its summary.
6. Confirm that `data/listings.csv` was updated and committed by `house-listing-bot`.

The workflow already grants itself `contents: write`. If pushing fails, open:

**Settings → Actions → General → Workflow permissions → Read and write permissions**

Then run it again.

## Optional Telegram notifications

The workflow can message you only when a listing is new, changes price, changes open-house details, becomes active again, or disappears for three consecutive scans.

1. In Telegram, message **@BotFather**, create a bot and copy its token.
2. Send one message to your new bot.
3. Find your numeric chat ID using Telegram's `getUpdates` endpoint or a chat-ID helper bot.
4. In the GitHub repository, open **Settings → Secrets and variables → Actions**.
5. Add these repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

The scan still works without these secrets; it simply skips Telegram.

## Change the search later

Edit `config.json`. Keep both:

- `search_url`: the human-readable saved-search URL
- `query`: the parameters sent to the JSON endpoint

For example, to change the price range, edit:

```json
"price": "65000000,80000000"
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python scanner.py
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## Notes and limitations

- GitHub scheduled workflows can be delayed; they are not exact real-time alerts.
- This project uses an unofficial public endpoint observed behind the search page. Respect the site's terms and keep the scan frequency modest.
- Open-house information is saved when it is included in the search response. Some listings may expose it only on the detail page; this starter does not crawl every detail page.
- A listing is marked `inactive` only after it is absent for three successful scans, reducing false removals caused by temporary endpoint issues.
- Keep the repository private if you add personal notes or notification credentials.
