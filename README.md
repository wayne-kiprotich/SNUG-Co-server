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
- The proxy passes the original `Host` header. The admin API rejects requests whose `Origin` doesn't match it. Set `TRUSTED_PROXIES=1` if the proxy sets `X-Forwarded-*` headers.
- `UPLOAD_DIR` points to a disk that survives redeploys, and it is backed up. Uploaded photos are files, not database rows.
- For PostgreSQL, install `requirements-postgres.txt` and set `DATABASE_URL`. Run `flask db upgrade` after every update.
- Build the client with `VITE_API_URL=/api` so the storefront reads the live catalog.
- Add rate limiting to `/api/admin/login` at the proxy as well. The app's own limit (5 wrong tries per 15 minutes per address and email) resets on restart and isn't shared between workers.

## Security notes

- Passwords are hashed with scrypt. The same message and timing is used for a wrong email and a wrong password.
- The session is a signed cookie (`HttpOnly`, `SameSite=Lax`, 8 hours). It can't be revoked individually. Rotate `SECRET_KEY` to sign everyone out.
- Every state-changing admin request must carry `X-Requested-With: snug-admin` and, when the browser sends one, a matching `Origin`. Other websites can't send that header.
- Uploads are decoded and re-encoded with Pillow, so the file's real contents are checked and only WebP is written. Limits: JPEG, PNG or WebP, 600px wide or more, 16 MB each, 12 per product.
- The public API only returns products marked visible.

## Not built

- **Cloudinary or ImageKit.** Photos are stored on local disk through `LocalStorage` in `app/images.py`. To use a hosted service, write a class with the same `save` and `delete` methods. That needs an account and keys from SNUG, so it wasn't done.
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
| `app/cli.py` | `seed`, `create-admin`, `reset-password` |
| `migrations/` | Database migrations |
| `seed/catalog.json` | Starter catalog, made with `npm run export-catalog` in `client/` |
