# UNDP Funding Radar

Every morning at 08:00 Tashkent time, this tool checks your list of websites for new calls for proposals, grants and tenders. It sends the new ones to your Telegram and lists everything on a small website you can search.

**Cost: $0.** It runs on GitHub, which is free for this use. There is no server to rent and no hosting to pay for.

- **GitHub Actions** runs the check every day (free).
- **GitHub Pages** hosts the dashboard website (free).
- **Telegram Bot API** sends the messages (free).

---

## What it does

1. Opens every website in `sites.yaml`. It reads normal web pages, RSS feeds and, if needed, JavaScript-heavy sites.
2. Keeps only links that look like funding opportunities, such as "call for proposals", "grant" or "request for proposals". It skips jobs, scholarships and similar pages.
3. Opens each new opportunity page to find the **deadline** and the **eligible geography**.
4. **Geography filter:** it keeps calls for Uzbekistan, Central Asia or the wider region, global calls, and calls that don't name a geography. It drops calls limited to other countries, for example "Grant for SMEs (Malta)".
5. It sends only **new** items to Telegram, so nothing is sent twice. The first time it reads a new website, it saves that site's current listings to the dashboard without sending them to Telegram, so you don't get a flood of messages.
6. It updates the dashboard and a **website status** table. The table shows which sites worked and which need attention.

---

## Setup (about 20 minutes, one time only)

### Step 1: Create a free GitHub account
1. Go to **github.com** and click **Sign up**.
2. Enter your email, a password and a username. Your username becomes part of your dashboard address: `https://USERNAME.github.io/funding-radar/`.
3. Verify your email.

### Step 2: Create the repository and upload the files
1. On GitHub, click **+** (top right), then **New repository**.
2. Name: `funding-radar`. Choose **Public**. GitHub Pages and unlimited free runs need a public repository. Your Telegram keys stay secret either way (see Step 4).
3. Click **Create repository**.
4. On the next page, click **uploading an existing file**.
5. Unzip `funding-radar.zip` on your computer. Open the unzipped folder, select **everything inside it** and drag it into the GitHub page. Click **Commit changes**.

> ⚠️ The `.github` folder is hidden on some computers. If you don't see it after uploading, the daily schedule won't exist. To fix this, in your repository click **Add file**, then **Create new file**. Type the name `.github/workflows/scrape.yml`, paste in the contents of `scrape.yml` from the zip, and click **Commit changes**.

### Step 3: Create your Telegram bot
1. In Telegram, search for **@BotFather** (the official one has a blue check mark) and press **Start**.
2. Send `/newbot`. Choose a display name, such as *Funding Radar*, and then a username ending in `bot`, such as `nargiza_funding_bot`.
3. BotFather replies with a **token** that looks like `7412345678:AAH...`. Copy it and keep it private.
4. Open your new bot in Telegram and press **Start**. Send it any message, such as "hi".
5. Get your **chat ID**. In your browser, open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   and replace `<YOUR_TOKEN>` with your token. Find `"chat":{"id":123456789` and copy the number.
   - *Want to send it to a team group or channel instead?* Add the bot to the group, post a message there, open the same link again, and use that chat's ID. It starts with `-100…`. For several chats, separate the IDs with commas.

### Step 4: Add the keys to GitHub as secrets
1. In your repository, go to **Settings**, then **Secrets and variables**, then **Actions**, then **New repository secret**.
2. Name: `TELEGRAM_BOT_TOKEN`. Value: your token. Click **Add secret**.
3. Add another secret. Name: `TELEGRAM_CHAT_ID`. Value: your chat ID.

Secrets are encrypted. Nobody who visits your repository can see them.

### Step 5: Allow the tool to save its results
Go to **Settings**, then **Actions**, then **General**. Scroll to **Workflow permissions**, choose **Read and write permissions**, and click **Save**.

### Step 6: Turn on the dashboard website
Go to **Settings**, then **Pages**. Under **Build and deployment**, set **Source: Deploy from a branch** and **Branch: `main`**, folder **`/docs`**. Click **Save**.
After a minute or two, your dashboard is live at `https://USERNAME.github.io/funding-radar/`.

### Step 7: Test it
1. Go to the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.
2. Click **Daily funding scan** on the left, then **Run workflow**. Tick **Only send a test Telegram message** and run it. You should receive "✅ UNDP Funding Radar is connected."
3. Run it again **without** the tick. This is the first real scan. Telegram tells you how many current listings were saved from each site, and the dashboard fills up.

From now on it runs automatically every morning. You don't need to keep your computer on.

---

## Adding or changing websites

Open `sites.yaml` on GitHub, click the ✏️ pencil icon, edit, and click **Commit changes**. The change takes effect at the next run, or right away if you click **Run workflow**.

```yaml
  - name: EU Delegation Uzbekistan
    url: https://example.org/calls-for-proposals
    type: html
```

**If a site shows 0 listings or wrong items** in the dashboard's *Website status* table, add one of these settings:

| Problem | Fix |
|---|---|
| The page picks up menu links or unrelated pages | `link_pattern: /call-for-proposals/`. Use text that every real opportunity link contains; you can see it by hovering over a link in your browser. |
| The page shows 0 listings but the list is visible in the browser | `js: true`. The site builds its list with JavaScript. This option is slower but works. |
| You know the exact element that holds the list | `item_selector: ".views-row h3 a"` |
| All links on a page are calls, but their titles lack keywords | `require_keywords: false` |
| A site gives too many calls from other countries | `geography_mode: strict` (for this site only) |
| The site is temporarily broken | `enabled: false` |

**Three portals are read through their free public data APIs** instead of their web pages, because their pages load with JavaScript: **EU Funding & Tenders** (which also covers INTPA/EuropeAid calls), **Grants.gov** (including U.S. Embassy calls) and **World Bank procurement**. Each one searches for the words in its `query:` line, for example `query: [Uzbekistan, Central Asia]`. Edit that line to search for other words.

Sites switched off with `enabled: false` have the reason written next to them, such as paid subscription, login required, other region only, or closed. Change `false` to `true` to try any of them.

If a site has an **RSS feed** (look for an RSS icon or a `/feed` address), use it with `type: rss`. Feeds are the most reliable option.

## Other settings (top of `sites.yaml`)
- `geography_mode`: `relaxed` (default), `strict` (only calls that explicitly name Uzbekistan, the region or global eligibility) or `off`.
- `opportunity_keywords` / `exclude_keywords`: what counts as a call and what to ignore.
- `notify_when_empty: true`: also get a message on days with nothing new.
- **Change the time:** edit the `cron` line in `.github/workflows/scrape.yml`. It uses UTC time. `0 3 * * *` means 03:00 UTC, which is 08:00 in Tashkent.

## Good to know
- **Free limits:** public repositories get unlimited free GitHub Actions minutes. A daily run takes about 1–3 minutes.
- **Keep it active:** GitHub pauses scheduled workflows if a repository has no activity for 60 days. The daily result saves count as activity, so this normally doesn't happen. If the Actions tab ever says the workflow is disabled, click **Enable**.
- **First run:** the first scan of a new site builds a baseline. It saves the site's current listings to the dashboard and doesn't send them to Telegram. With about 30 sites, the first run can take 20–40 minutes; daily runs after that are much faster.
- **Start over:** to have every item treated as new again, replace the contents of `data/seen.json` with `{"sites": {}, "ids": {}}`.
- **Be polite to websites:** the tool waits between requests and opens at most 25 new pages per site per day. Please respect each website's terms of use.
- **Limits:** the Telegram bot only sends messages. It doesn't answer commands, because that would need a paid server running all the time. Use the dashboard to search.

## Files
```
sites.yaml                    ← your settings and website list (edit this)
scraper/                      ← the Python program
.github/workflows/scrape.yml  ← the daily schedule
docs/index.html               ← the dashboard
docs/data/*.json              ← saved opportunities and site status (updated automatically)
data/seen.json                ← memory of what was already seen (updated automatically)
```

Run locally (optional, for technical users): `pip install -r requirements.txt && python -m scraper.main --dry-run`
