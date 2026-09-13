Dr. Syed Farukh Shah – Spiritual Healer

FastAPI website with public pages, admin dashboard, SQLite CMS storage, media uploads, WhatsApp configuration, and moderated comments.

Run locally:

  cd spiritual-healer
  python3 -m pip install -r requirements.txt
  export ADMIN_PASSWORD='choose-a-strong-password'
  export SESSION_SECRET='use-a-long-random-secret'
  uvicorn app:app --host 0.0.0.0 --port 8000

Public website: http://localhost:8000/
Admin dashboard: http://localhost:8000/admin
Default username: admin

Railway deployment:

Railway start command:

  uvicorn app:app --host 0.0.0.0 --port $PORT

Required Railway environment variables:

  ADMIN_USER=admin
  ADMIN_PASSWORD=choose-a-strong-password
  SESSION_SECRET=choose-a-long-random-secret

Recommended Railway persistence:

This app uses SQLite and uploaded local files. For production, add a Railway volume and mount it so these paths persist:

  /app/data
  /app/static/uploads

Security notes:

- Do not commit data/admin-password.txt, .env files, tokens, or secret keys.
- .gitignore and .dockerignore already exclude local secrets.
- Set ADMIN_PASSWORD and SESSION_SECRET in Railway variables, not in source code.

Content notes:

- Demo content is seeded automatically if the database is empty.
- Demo media assets are stored under static/uploads and can be edited, hidden, replaced, or deleted from the admin dashboard.
- Pillow is used for automatic image resizing/conversion to WebP when available.
