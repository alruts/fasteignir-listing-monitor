# Fasteignir.is listing monitor

A small personal monitor for apartment listings in Reykjavík on [fasteignir.is](https://fasteignir.is).

## Filters

Applied in Python after fetching from the API:

- **Property type:** Fjölbýlishús (apartments) only
- **Price:** 65,000,000–80,000,000 ISK
- **Size:** up to 120 m²
- **Postcodes:** 101 and 107 (configured in `config.json`)

## Schedule

The workflow runs on GitHub-hosted machines at approximately **08:07, 13:07 and 19:07 Iceland time** every day. Your own computer can be off. The seven-minute offset avoids the busiest exact-hour period for scheduled GitHub Actions.

## What it stores

`data/listings.csv` is the human-readable database with these columns:

| Column | Description |
|---|---|
| `listing_id` | Unique property ID |
| `url` | Link to the listing on fasteignir.is |
| `address` | Street name and number |
| `postcode` | Postal code |
| `price_isk` | Asking price in ISK |
| `size_m2` | Size in square metres |
| `rooms` | Number of rooms |
| `bedrooms` | Number of bedrooms |
| `bathrooms` | Number of bathrooms |
| `property_type` | e.g. Fjölbýlishús |
| `open_house` | Sortable ISO date + time range (e.g. `2026-07-15, 17:00–17:30`) |
| `listed_date` | When the listing was published |
| `status` | `active` or `inactive` |
| `change_type` | What changed: `new`, `price`, `open_house`, `reactivated`, `inactive` |
| `previous_price_isk` | Previous price if a price change was detected |

`data/latest_changes.json` contains only changes from the latest successful scan.

The scraper uses the site's JSON search endpoint rather than clicking through the web interface. Because this is an unofficial endpoint, the site can change it. When parsing fails, the Action fails visibly instead of silently replacing the database.

## Set up on GitHub

1. Create a GitHub repository.
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

Edit `config.json` to adjust the API query parameters. The Python filters in `scanner.py` (price, size, property type) are applied on top of the API results.

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
- Open-house information is saved when it is included in the search response. Some listings may expose it only on the detail page; this project does not crawl every detail page.
- A listing is marked `inactive` only after it is absent for three successful scans, reducing false removals caused by temporary endpoint issues.
