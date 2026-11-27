# Krillion - Static Edition for GitLab Pages

A 100% static, zero-backend single-player version of **Krillion ("The Daily Dive")** built with Vite, React, TypeScript, and HTML5 Canvas, ready to deploy on **GitLab Static Pages**.

## Included Features

- **Daily Dive**: 7 prompts per day, 25 seconds per prompt, resetting at midnight Eastern Time (`America/New_York`). Uses a deterministic permutation cycle across **4,127 prompts** (**589 consecutive days** with zero repeated prompts), **1,131,554 answers**, and **473,690 Wikidata English aliases**.
- **6 Rarity Tiers & Depth Scoring**: `Plankton` (5 pts / 50m), `Too Clever` (15 pts / 150m), `Schooler` (30 pts / 300m), `Rare` (60 pts / 600m), `Deep Cut` (85 pts / 850m), and `One in a Krillion` (100 pts / 1,000m), up to 7,000m in the Hadal Zone.
- **All Single-Player Modes Free & Unlocked**:
  - **Archive** (`#/archive`): Replay past Daily Dives from `#1` up to yesterday.
  - **Themed Packs** (`#/packs`): 4 themed packs (Words & Language, At the Movies, Sports, Geography), 5 chapters each.
  - **Unlimited** (`#/unlimited`): Endless 7-prompt dives across the full catalog.
  - **Wardrobe & Streaks**: 9 pixel-art Dive Buddies unlocked by daily streaks, saved in `localStorage`.
  - **My Krillion Logbook** (`#/account`) & **Settings**: Low-power mode, Colorblind mode, Answer corrections (fuzzy typo preview), Clear rejected entries, Sound toggle (Web Audio retro synth), and Share link toggle.

---

## Deploying to GitLab Static Pages

This project is preconfigured for GitLab Pages:
- `.gitlab-ci.yml` defines the `pages` job (`npm ci` -> `npm run test` -> `npm run build` -> copies `dist/` to `public/`).
- `vite.config.ts` sets `base: './'` and `src/App.tsx` uses hash routing (`#/...`), so the game works on both **project subpaths** (`https://<username>.gitlab.io/<repo>/`) and **custom domains** without extra configuration.

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
   - Note: GitLab.com shared runners must be enabled on the project (enabled by default under **Settings -> CI/CD -> Runners**).
4. **Open your live game**:
   - Go to **Deploy -> Pages** in your GitLab project sidebar.
   - Click the listed Pages URL (typically `https://<your-username>.gitlab.io/<your-repo>/`, or the unique domain URL if **Use unique domain** is checked in Pages settings - either works).
   - Optional: Under **Deploy -> Pages**, uncheck **Use unique domain** if you prefer the cleaner `https://<username>.gitlab.io/<repo>/` URL, or click **New Domain** to attach a custom domain.

### Option B: Upload Files in the GitLab Web UI (No Git CLI)

1. Create a blank GitLab project.
2. Unzip `krillion-gitlab-project.zip` locally and upload all files (including hidden files `.gitlab-ci.yml` and `.gitignore`) to the default branch, or use GitLab's Web IDE to import the folder.
3. Commit to the default branch; GitLab CI will run `.gitlab-ci.yml` and publish to **Deploy -> Pages**.

---

## Local Development & Commands

Requires Node.js 20+ (tested on Node 24):

```bash
npm install      # Install dependencies
npm run dev      # Start local dev server (http://localhost:5173/)
npm run test     # Run Vitest unit & chunk-integrity tests
npm run build    # Type-check and build production bundle into dist/
npm run preview  # Preview the production build locally
```

## Updating or Expanding the Prompt Database

All 4,127 prompts, 1,131,554 answers, and 473,690 aliases are stored as 256 static JSON chunks under `public/data/chunks/chunk-000.json` through `chunk-255.json`, indexed by `src/data/manifest.ts`.

To regenerate or customize the dataset (requires Python 3):
- Edit `scripts/seed_prompts.json` or `scripts/build_year_database.py`.
- Run `python3 scripts/build_year_database.py` to rebuild `public/data/chunks/` and `src/data/manifest.ts`.
- Run `npm run test && npm run build` before committing and pushing to GitLab.
