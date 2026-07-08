# Deploy Runbook — PythonAnywhere Cutover

Account: `bercik29` · Old app: `/home/bercik29/cernyfoot` (untouched — it is the rollback)
New app: `/home/bercik29/cernyfoot-v2`

> **Free-tier note:** PythonAnywhere free accounts allow ONE web app, so v2 replaces
> the old app at the same URL. The old code and CSVs stay on disk untouched;
> rollback is repointing one WSGI file (step 9).

---

## 0. Pre-flight (one-time, before cutover day)

- [ ] In a PythonAnywhere Bash console: `python3.10 --version` (any ≥ 3.9 works —
      needed for `zoneinfo`). Note the exact version for the venv below.
- [ ] Push this repo to GitHub (private repo is fine) so PA can `git clone` it,
      or upload a zip via the Files tab.
- [ ] Read `scripts/output/migration_report.md` once more — the reconciliation
      decisions (D1/D2, auto-cancel, guests) are what production will contain.

## 1. Install

```bash
cd ~
git clone <your-repo-url> cernyfoot-v2       # or unzip the upload
cd cernyfoot-v2
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. Configure

```bash
cp .env.example .env
python3.10 -c "import secrets; print(secrets.token_hex(32))"   # → paste as SECRET_KEY
nano .env    # set SECRET_KEY=<generated>, FLASK_CONFIG=prod
```

The app **refuses to boot in prod without a real SECRET_KEY** — a blank one cannot
slip through.

## 3. Create the schema

```bash
cd ~/cernyfoot-v2
FLASK_APP=wsgi.py .venv/bin/flask db upgrade
```

## 4. Migrate the live data (the cutover moment)

Do this on the evening you switch, so no sign-ups are lost between export and go-live
(ideally not a Thursday):

```bash
.venv/bin/python -m scripts.migrate_csv --source /home/bercik29/cernyfoot/static
cat scripts/output/migration_report.md   # read the warnings section!
```

The migration is idempotent — re-running it wipes and re-imports, so a second run
after fixing anything is safe **until people start using v2** (then never run it
again: it would erase post-cutover data).

## 5. Point the web app at v2

On the **Web** tab:

1. *Source code:* `/home/bercik29/cernyfoot-v2`
2. *Virtualenv:* `/home/bercik29/cernyfoot-v2/.venv`
3. Edit the **WSGI configuration file** to exactly:

```python
import sys
sys.path.insert(0, "/home/bercik29/cernyfoot-v2")
from wsgi import app as application
```

4. *Static files mapping:* URL `/static/` → `/home/bercik29/cernyfoot-v2/app/static/`
5. **Reload** the web app.

## 6. Smoke-test (5 minutes)

- [ ] `https://<domain>/health` → `{"status": "ok"}`
- [ ] `/calendar` shows the seasons and past results
- [ ] Log in as `berco` → claim flow → set your real password
- [ ] `/admin/` loads; `/stats` numbers look right
- [ ] Anonymous browser: POST-y things are locked (try visiting `/admin/` — 403/login)

## 7. Tell the group

Message for the WhatsApp/group chat, in spirit:
> Nová prihlasovačka je nasadená na tej istej adrese. Prvé prihlásenie: zadaj svoju
> prezývku a nastav si heslo. Kto skôr príde, ten si svoju prezývku zaberie — tak
> neváhajte. 🙂

**Admins (berco, frido, michal, tomasc) should claim their nicknames immediately**
— first-claim-wins is the one soft spot of the claim flow, and admin accounts
matter most.

## 8. Nightly backup (right after cutover)

On the **Tasks** tab create a daily task (e.g. 03:00 UTC):

```bash
/home/bercik29/cernyfoot-v2/.venv/bin/python -m scripts.backup_db --db /home/bercik29/cernyfoot-v2/instance/cernyfoot.db --dest /home/bercik29/backups --keep 14
```

The script verifies each backup with `PRAGMA integrity_check` and prunes to the
newest 14. Check the task log after the first night. To test a restore:
`sqlite3 /home/bercik29/backups/<newest>.db "SELECT count(*) FROM players;"`

## 9. Rollback (if anything is wrong)

The old app is fully intact. On the Web tab: set source/virtualenv/WSGI back to the
old `cernyfoot` paths, reload. The CSVs were only ever **read** by the migration.

## 10. After a stable week

- [ ] Archive `~/cernyfoot` (`zip -r cernyfoot-old-final.zip cernyfoot`) and download
      a copy — the last CSV state, kept forever.
- [ ] Delete the temporary `login_jon`-era experiments from your bookmarks. 🙂
- [ ] Before the 2026/2027 season: Admin → Sezóny → create the season, add the new
      year's holidays, press "Vygenerovať zápasy". No code deploy needed.
