# Snug & Co. server and admin

A Flask API that stores the catalog in a database and lets the team manage it from the admin at `/admin` on the website. The storefront reads from this API when `VITE_API_URL` is set.

What the admin can do (PRD §37):

- Sign in with an email and password (no public sign-up)
- Add, edit, hide and delete products, and change their order
- Change prices, mark a piece sold out or coming soon, feature it, or flag it as a new arrival
- Set colours (with swatches), sizes and extra options such as pants or shorts
- Upload photos, reorder them, write their descriptions and remove them
- Add, edit, reorder and delete categories and collections, and choose their cover photos
- Change their own password

Not included: staff accounts with different permissions, editing the site settings (WhatsApp number, hours, policies), testimonials, and orders. Those still live in `client/src/config/site.js` and `client/src/data/social.js`.

## Set up

```bash
cd server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # add -postgres.txt for PostgreSQL

cp .env.example .env                                # then set SECRET_KEY (see the file)
export FLASK_APP=wsgi.py

.venv/bin/flask db upgrade                          # create the tables
.venv/bin/flask seed                                # load the 23 products from the storefront
.venv/bin/flask create-admin                        # asks for an email and password (12+ characters)
.venv/bin/flask run --port 5000
```

In another terminal, run the site against it:

```bash
cd client
echo "VITE_API_URL=/api" >> .env
npm run dev                                         # http://localhost:5173, admin at /admin
```

The dev server proxies `/api` and `/uploads` to port 5000, so the site and API behave as one domain.

Forgot a password: `flask reset-password`.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Deploying

The admin's sign-in cookie only works when the site and the API share one domain, so serve both from the same host: the built site from `client/dist`, and `/api` and `/uploads` proxied to Flask.

```nginx
location /api/     { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Forwarded-Proto $scheme; }
location /uploads/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
location /         { root /var/www/snug/dist; try_files $uri /index.html; }
```

```bash
.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 wsgi:app
```

Checklist:

- `SECRET_KEY` is set to a long random value and never committed. Changing it signs everyone out.
- `FLASK_DEBUG` is `0` (or unset). Cookies are then marked `Secure`, so the site must use HTTPS.
- The proxy passes the original `Host` header. The admin API rejects requests whose `Origin` doesn't match it (or an address in `ALLOWED_ORIGINS`). Set `TRUSTED_PROXIES=1` if the proxy sets `X-Forwarded-*` headers.
- `UPLOAD_DIR` points to a disk that survives redeploys, and it is backed up — or set `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` to skip local disk entirely (see below). Uploaded photos are files, not database rows.
- For PostgreSQL, install `requirements-postgres.txt` and set `DATABASE_URL`.
- Build the client with `VITE_API_URL` pointing at this API, then run `flask db upgrade` after every schema change.
- Add rate limiting to `/api/admin/login` at the proxy as well. The app's own limit (5 wrong tries per 15 minutes per address and email) resets on restart and isn't shared between workers.

## Deploying the client on its own domain

If the client is a separate app (its own repo, its own host — Vercel, Netlify, …) rather than built into this server's `CLIENT_DIST`, cookies and requests cross a domain boundary and need a bit more:

- Recommended: let the client's host proxy `/api` and `/uploads` to this server (`client/vercel.json` does this) and build the client with `VITE_API_URL=/api`. The sign-in cookie is then first-party, so browsers that block third-party cookies (Safari, Brave) still work.
- Set `ALLOWED_ORIGINS` to the client's exact origin(s), e.g. `https://snug-co-client.vercel.app`. The admin rejects change requests from any other origin, and CORS headers are sent only to these.
- Only if the browser calls this API's own domain directly (no proxy): set `SESSION_COOKIE_SAMESITE=None` and `VITE_API_URL` to the full API address. Both sites must use HTTPS.
- Photos need a store reachable by URL regardless of which host serves them — see Supabase Storage below. A local disk only serves photos on the same host that saved them.

## Storing photos: local disk or Supabase Storage

Photos are files, written at a few widths after upload. `app/images.py` has two storage backends with the same `save`/`delete` interface:

- **Local disk** (default): fine for one machine, or a Render service with a persistent disk. Render's *free* tier has no persistent disk — anything saved there is lost on the next deploy or restart.
- **Supabase Storage**: set `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (the service_role key, not anon — Project Settings → API) and `SUPABASE_BUCKET` (create it first: Storage → New bucket → Public bucket on). Photos are then durable regardless of Render's plan, and reachable from any host, which is what cross-domain deployment needs anyway.

The storefront's 23 seeded products point at photos that ship inside the *client's* repo (`client/public/images`), not this one. Those never touch this server unless you move them. To make every photo come from this API instead of the client bundle, run once, from a machine with both repos checked out side by side:

```bash
export FLASK_APP=wsgi.py
flask import-bundled-photos
```

It uploads each bundled photo to the configured storage, and flips its database row so the API starts returning that photo's real URL instead of leaving the client to resolve it locally. Safe to re-run; it skips photos already migrated. After it finishes, `client/public/images` and `client/src/data/image-manifest.json` are no longer needed by a deployed client — keep them only if you want the site to still work with no backend configured at all.

## Security notes

- Passwords are hashed with scrypt. The same message and timing is used for a wrong email and a wrong password.
- The session is a signed cookie (`HttpOnly`, `SameSite=Lax`, 8 hours idle, 7 days at most). Changing the password (in the admin or with `flask reset-password`) signs out every other browser. Rotate `SECRET_KEY` to sign everyone out.
- Sign-in attempts are limited per browser: one that has signed in before carries a signed device cookie and has its own limit, so someone hammering the login from a shared proxy address can't lock the owner out.
- Requests are capped at 64 KB, except photo uploads (40 MB). Photos over 40 megapixels (PNG/WebP) are rejected before decoding; large JPEGs are decoded at reduced size.
- Every state-changing admin request must carry `X-Requested-With: snug-admin` and, when the browser sends one, a matching `Origin`. Other websites can't send that header.
- Uploads are decoded and re-encoded with Pillow, so the file's real contents are checked and only WebP is written. Limits: JPEG, PNG or WebP, 600px wide or more, 16 MB each, 12 per product.
- The public API only returns products marked visible.

## Not built

- **Database backups and audit logs.** There is no record of who changed what.

## Layout

| Path | What it holds |
| --- | --- |
| `app/models.py` | Tables: products, images, categories, collections, admin users |
| `app/routes/public.py` | `GET /api/catalog` for the storefront |
| `app/routes/auth.py` | Sign in, sign out and change password |
| `app/routes/admin.py` | Product, photo, category and collection endpoints |
| `app/validation.py` | Input checks, with a message for each field |
| `app/images.py` | Photo cropping, resizing and storage |
| `app/cli.py` | `seed`, `create-admin`, `reset-password`, `import-bundled-photos` |
| `migrations/` | Database migrations |
| `seed/catalog.json` | Starter catalog loaded by `flask seed` |

## Production on Render (one service, one domain)

`render.yaml` at the repo root builds the React site, installs the server, runs `flask db upgrade`, and starts gunicorn. Flask serves the built site, `/api`, and page routes (direct links work). After the first deploy, set `VITE_WHATSAPP_NUMBER`, `VITE_SITE_URL` and `VITE_GOOGLE_SITE_VERIFICATION` in the Render dashboard, redeploy, then run `flask seed` and `flask create-admin` in the Render shell.

Uploaded photos are saved to a 1 GB Render disk mounted at `/var/data` (`UPLOAD_DIR=/var/data/uploads`) and served from `/uploads`. Turn on Cloudflare's proxy for the domain so photos are cached near customers; they are sent with a one-year cache header.
