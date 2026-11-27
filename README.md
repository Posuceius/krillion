# Krillion - Static Edition for GitLab Pages

A 100% static, zero-backend single-player version of **Krillion ("The Daily Dive")** built with Vite, React, TypeScript, HTML5 Canvas, and **Static SQLite over HTTP (`sql.js-httpvfs`)**, ready to deploy from a **single GitLab repository** on **GitLab Static Pages**.

## Included Features

- **Full-Year Broad Trivia Catalog (Zero Repeats for 403 Days)**:
  - **2,822 daily-eligible broad trivia prompts** (**403 consecutive days** with zero repeated prompts in Daily Dive and Unlimited), with no robotic `"word starting with X"` or `"N-letter word"` clutter (`2,830` total prompts including 8 themed-pack rounds).
  - **2,186,936 answer links** across **739,914 entities** and **1,975,539 searchable forms**, including mega-pools up to **100,000 answers** (`geo-world-city`, `mov-any-movie`), **40,000** (`gen-tv-show`), and **10,000-15,000+** (`geo-river`, `gen-composer`, `geo-mountain`, `geo-island`, `mov-director`, `spt-footballer`).
- **Static SQLite over HTTP (Single-Repo Architecture)**:
  - Compiled into a **184.91 MiB** indexed SQLite database split into **19 static 10 MiB chunks** under `public/data/db/krillion.sqlite3.000` through `krillion.sqlite3.018` (with `sqlite.worker.js`, `sql-wasm.wasm`, and `config.json`).
  - The browser never downloads the full database: `sql.js-httpvfs` issues standard HTTP `Range` requests for tiny 4 KB B-tree pages per guess (<50 ms lookup even on 100,000-answer prompts).
- **Human-Friendly Matching (Fewer `NO ECHO` Rejections)**:
  - **Surnames on person prompts**: `Mozart`, `Beethoven`, `Messi`, `Spielberg`, `Einstein`, `da Vinci`.
  - **Optional category prefixes/suffixes & abbreviations**: `Everest` / `Mt Everest` for `Mount Everest`, `Yellowstone National Park` for `Yellowstone`, `Victoria` for `Lake Victoria`, `St Lucia` for `Saint Lucia`.
  - **Roman numerals & subtitles**: `Rocky 2` matches `Rocky II`, `Toy Story III` matches `Toy Story 3`, `Fellowship of the Ring` matches full titles.
  - **Wikidata / GeoNames / IMDb aliases & indexed fuzzy typos**: `Boneiru` -> `Bonaire`, `acetylsalicylic acid` -> `aspirin`, `Bonaier` -> `Bonaire`, `Everst` -> `Mount Everest`.
- **All Single-Player Modes Free & Unlocked**:
  - **Daily Dive**, **Archive** (`#/archive`), **Themed Packs** (`#/packs`), **Unlimited** (`#/unlimited`), **Wardrobe & Streaks** (9 pixel-art Dive Buddies in `localStorage`), **My Krillion Logbook** (`#/account`), **Live Depth Plunge Animation**, and **Settings**.

---

## Deploying to GitLab Static Pages (Single Repository)

This project is preconfigured for a **single GitLab repository**:
- `.gitlab-ci.yml` uses `image: node:24-alpine` and defines the `pages` job (`npm ci` -> `npm run test` -> `npm run build` -> copies `dist/` to `public/`).
- Every database chunk in `public/data/db/` is <= 10 MiB (well under Git/GitLab file limits), and Vite copies `public/data/db/` directly into `dist/data/db/`.
- `vite.config.ts` sets `base: './'` and `src/App.tsx` uses hash routing (`#/...`), so relative HTTP `Range` requests for `./data/db/krillion.sqlite3.*` work on both **project subpaths** (`https://<username>.gitlab.io/<repo>/`) and **custom domains**.

### Option A: Push via Git CLI (Recommended)

1. **Create an empty project in GitLab**:
   - Go to GitLab -> **New project** -> **Create blank project**.
   - Uncheck **Initialize repository with a README** so the repo starts empty.
2. **Extract `krillion-gitlab-project.zip`** into a folder and push it to your new GitLab repository:
   ```bash
   mkdir krillion && cd krillion
   unzip /path/to/krillion-gitlab-project.zip

   git init -b main
   git add .
   git commit -m "Initial Krillion static site"
   git remote add origin https://gitlab.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
   *(If your GitLab project's default branch is named `master`, use `-b master` and `git push -u origin master` instead - `.gitlab-ci.yml` automatically watches `$CI_DEFAULT_BRANCH`.)*
3. **Wait for the CI pipeline to finish**:
   - In GitLab, open **Build -> Pipelines** and wait for the `pages` job to pass (green checkmark).
   - GitLab.com shared runners must be enabled on the project (enabled by default under **Settings -> CI/CD -> Runners**).
4. **Open your live game**:
   - Go to **Deploy -> Pages** in your GitLab project sidebar and click your Pages URL.

### Option B: Upload Files in the GitLab Web UI (No Git CLI)

1. Create a blank GitLab project.
2. Unzip `krillion-gitlab-project.zip` locally and upload all files (including `.gitlab-ci.yml`, `.gitignore`, and `public/data/db/`) to the default branch.
3. Commit to the default branch; GitLab CI will run `.gitlab-ci.yml` and publish to **Deploy -> Pages**.

---

## Local Development & Commands

Requires Node.js 24+ (for built-in `node:sqlite` in tests):

```bash
npm install      # Install dependencies
npm run dev      # Start local dev server (http://localhost:5173/)
npm run test     # Run Vitest unit & chunked SQLite integrity tests
npm run build    # Type-check and build production bundle into dist/
npm run preview  # Preview the production build locally
```

## Updating or Rebuilding the SQLite Database

The database is generated by `scripts/build_sqlite_database.py` (Python 3) from:
- Curated seeds (`scripts/seed_prompts.json`)
- Bulk GeoNames (`cities500.zip`, `countryInfo.txt`, `admin1CodesASCII.txt`) and IMDb (`title.basics.tsv.gz`, `title.ratings.tsv.gz`) dumps
- Sitelink-banded batched Wikidata SPARQL queries + English `skos:altLabel` aliases

To rebuild `public/data/db/` and `src/data/manifest.ts`:
```bash
python3 -u scripts/build_sqlite_database.py
npm run test && npm run build
```
