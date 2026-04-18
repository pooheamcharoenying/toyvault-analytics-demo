# ToyVault Analytics — Demo

Public demo of a toy-distribution business analytics dashboard (a fictional company, anonymized dataset). Built with **FastAPI** + **Next.js**, designed to run as two Railway services from a single monorepo.

> All brand names, product names, channels, warehouses, customers and suppliers in this dataset are fictional. Numbers are derived from a real-world operation but scaled and trimmed so they cannot be tied to any specific business.

## Repository layout

```
toyvault-analytics-demo/
├── backend/      FastAPI + pandas analytics API
├── frontend/     Next.js 15 dashboard UI
├── scripts/      Data prep helpers (anonymization, downsize, rename)
└── README.md
```

## Running locally

### Prerequisites
- Python 3.10+
- Node.js 20+
- The anonymized Excel file (see "Data source" below)

### Backend
```bash
cd backend
python -m venv myenv
myenv/Scripts/pip install -r requirements.txt  # (on macOS/Linux: myenv/bin/pip)
cp .env.example .env
# Edit .env and set PUBLIC_MODE=true, point EXCEL_SOURCE_URL at your data file.
myenv/Scripts/python -m hypercorn app.main:app --bind "[::]:8000"
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev    # serves on http://localhost:3457
```

## Deploying to Railway

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app), create a **New Project** → **Deploy from GitHub repo**.
3. Add two services pointing to this same repo:
   - **backend** — Settings → Root Directory: `backend`, Watch Paths: `backend/**`
   - **frontend** — Settings → Root Directory: `frontend`, Watch Paths: `frontend/**`
4. For each service, click **Networking** → **Generate Domain** to get public URLs.
5. Set environment variables (see `.env.example` in each folder). Key ones:

**backend service:**
| Variable | Value |
|---|---|
| `PUBLIC_MODE` | `true` |
| `EXCEL_SOURCE_URL` | URL of the Excel file (GitHub Release asset, R2 public URL, etc.) |
| `ALLOWED_ORIGINS` | Your frontend's Railway URL |

**frontend service:**
| Variable | Value |
|---|---|
| `NEXT_PUBLIC_PUBLIC_MODE` | `true` |
| `API_BASE_URL` | `https://${{backend.RAILWAY_PUBLIC_DOMAIN}}` (Railway template) |
| `NEXT_PUBLIC_API_URL` | Same as `API_BASE_URL` |
| `API_BASIC_USER` | `public` (ignored in PUBLIC_MODE, but required by BFF routes) |
| `API_BASIC_PASS` | `public` |

6. Push a commit to `main`; Railway auto-deploys both services.

## Hosting the Excel data file

The Excel is ~100 MB which is over GitHub's 100 MB file limit. Options (pick one):

- **GitHub Releases** (free, simplest) — Create a release in your repo, upload the xlsx as an asset, then use the asset URL as `EXCEL_SOURCE_URL`.
- **Cloudflare R2** (free tier: 10 GB storage, no egress fees) — host the file there and use the public URL.
- **Git LFS** — free up to 1 GB storage / 1 GB monthly bandwidth. Commit the file normally; Railway pulls it on build.
- **Railway Volume** — attach a persistent disk to the backend service and upload once via Railway CLI.

The backend downloads the Excel at startup, caches it to `.excel_cache/`, and parses into memory.

## Credits

Built with assistance from Claude.
