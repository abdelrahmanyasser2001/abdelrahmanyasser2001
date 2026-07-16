# Setup

This repo has to be a special one: a repository whose **name matches your
username exactly** (`abdelrahmanyasser2001/abdelrahmanyasser2001`). GitHub
detects that and shows its README on your profile page automatically.

## 1. Create the repo
If you haven't already: new repo → name it exactly `abdelrahmanyasser2001`
→ public → initialize with a README (you'll overwrite it with the one here).

## 2. Push these files
```bash
git clone https://github.com/abdelrahmanyasser2001/abdelrahmanyasser2001.git
cd abdelrahmanyasser2001
# copy in: README.md, SETUP.md, today.py, requirements.txt,
#          templates/, cache/loc_cache.json, .github/workflows/update-readme.yml
git add .
git commit -m "profile readme with live stats"
git push
```

## 3. Create a Personal Access Token
The script needs to read your account's stats and (for the LOC count)
clone your repos. Use a **classic PAT**:

1. GitHub → Settings → Developer settings → Personal access tokens →
   Tokens (classic) → Generate new token
2. Scopes: `repo` (all) and `read:user`
3. Copy the token — you won't see it again

## 4. Add the token as a repo secret
In the `abdelrahmanyasser2001/abdelrahmanyasser2001` repo:
Settings → Secrets and variables → Actions → New repository secret
- Name: `ACCESS_TOKEN`
- Value: (the token from step 3)

## 5. Run it
Go to the Actions tab → "Update profile stats" → Run workflow (manual
trigger). After it finishes, `light_mode.svg` and `dark_mode.svg` in the
repo root will be filled in with your real numbers, and your profile page
will show them.

From then on it re-runs automatically every 12 hours (see the `cron` in
`.github/workflows/update-readme.yml` — change the schedule if you want it
more/less frequent).

## Notes / things to know
- The LOC counter works by shallow-cloning each of your **public** repos
  and running `git log --numstat`, filtered to commits authored by your
  GitHub username. Private repos are skipped (the token can see them, but
  counting private-repo LOC on a public profile would leak activity info
  about private work — remove that `if repo.get("isPrivate"): continue`
  guard in `today.py` if you want to include them).
- For a repo with a long git history, first run can take a while — the
  clone step has a 3-minute timeout per repo in `today.py`; bump it if a
  clone times out.
- `cache/loc_cache.json` is committed back after each run purely as a
  visible record of last-seen numbers per repo; the script currently
  recomputes from scratch each run rather than diffing against it. If your
  repo count grows a lot and runs get slow, that's the place to add
  incremental (commit-since-last-run) logic.
