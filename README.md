# AI Job-Application Cold-Email Agent

Reads your resume, collects job descriptions, pulls out the recruiter email and job ID,
has Claude score your fit and write a tailored cold email, then saves drafts or sends them
with your resume attached. Runs free on GitHub Actions every weekday morning.

## Files
```
job_agent.py                     the agent
requirements.txt                 Python packages
.github/workflows/job-agent.yml  the daily schedule on GitHub
.gitignore                       keeps .env out of the repo
.env.example                     settings template (for running on your laptop)
jds/                             drop job-description PDFs / .txt files here
```

## Hosting on GitHub (no command line needed)

### 1. Create the repo
github.com → **New repository** → name `job-agent` → **Private** → Create.

### 2. Upload the files
- Click **uploading an existing file**, unzip `job-agent.zip` on your computer, and drag in
  **everything inside the folder** (including the `.github` and `jds` folders) → **Commit changes**.
- Check that `.github/workflows/job-agent.yml` appears in the repo. If your computer hid the
  `.github` folder, create it by hand: **Add file → Create new file**, type the name
  `.github/workflows/job-agent.yml`, paste the file's contents, and commit.

### 3. Add your secrets
Repo → **Settings → Secrets and variables → Actions → Secrets → New repository secret**:

| Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your key from console.anthropic.com |
| `SMTP_USER` | your Gmail address |
| `SMTP_APP_PASSWORD` | a Gmail App Password (Google Account → Security → 2-Step Verification on → App passwords) |
| `RESUME_PDF_B64` | your resume as text, see below |

Turn your resume into text for `RESUME_PDF_B64`:
- **Windows (PowerShell):** `[Convert]::ToBase64String([IO.File]::ReadAllBytes("resume.pdf")) | Set-Clipboard`
- **Mac:** `base64 -i resume.pdf | pbcopy`
- **Linux:** `base64 -w0 resume.pdf`

Then paste it as the secret value. GitHub secrets max out at 48 KB; if yours is too big, skip
this secret and instead upload `resume.pdf` straight into the private repo.

### 4. Add your settings
Same page → **Variables** tab → **New repository variable**:

| Name | Example | Required |
|---|---|---|
| `YOUR_NAME` | `Deepak Reddy` | yes |
| `GREENHOUSE` | `razorpay groww` | optional, space-separated |
| `LEVER` | `cred` | optional |
| `KEYWORDS` | `backend python data` | optional, filters job titles |
| `MIN_SCORE` | `75` | optional, default 70 |
| `MAX_SEND` | `10` | optional, emails per run |
| `SEND_EMAILS` | `true` | leave unset until drafts look good |

### 5. Test it
**Actions** tab → enable workflows if asked → **Job agent** → **Run workflow**.
When it finishes, open the run and download **drafts** (a CSV of every job with the email Claude wrote).

### 6. Go live
Once the drafts read well, add the variable `SEND_EMAILS` = `true`. From then on it runs
automatically at 08:47 IST, Monday–Friday. To pause, delete that variable (drafts only) or
disable the workflow in the Actions tab.

## Adding jobs
- **From LinkedIn / Naukri / any site:** save the job page as PDF (Ctrl+P → Save as PDF) or
  paste it into a `.txt` file, then upload it to the `jds/` folder on GitHub. Recruiter posts
  that say "send your CV to x@company.com" work best.
- **Company career boards:** add the company's Greenhouse or Lever name to the variables
  (`boards.greenhouse.io/razorpay` → `razorpay`). Don't scrape LinkedIn with bots; it's against
  their terms and gets accounts restricted.

## How it avoids repeats
`out/sent_log.csv` is saved back to the repo after each run. A job is scored once, and nobody
is emailed twice. Good-fit jobs that were only drafted get sent on the first run with sending on.

## Running on your laptop instead
```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your values
python job_agent.py --resume resume.pdf --name "Your Name" --jd-dir jds          # drafts
python job_agent.py --resume resume.pdf --name "Your Name" --jd-dir jds --send   # send
```

## Good practice
- Keep volume low (10–20/day); mass identical emails land in spam and hurt your Gmail reputation.
- Only email addresses published for hiring, and stop if someone asks you to.
