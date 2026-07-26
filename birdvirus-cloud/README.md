# Birdvirus Cloud

Birdvirus Cloud is a small public chat UI with a private Node API behind it.

## Why the key is safe

The browser calls `POST /api/chat`; only `server.js` calls OpenAI. `OPENAI_API_KEY` lives in the deployment's environment variables or a local `.env` file, which is ignored by Git. Never put it in `index.html`, `app.js`, a GitHub secret exposed to Pages, or a `VITE_*`/`NEXT_PUBLIC_*` variable.

GitHub Pages can host the static frontend but **cannot run `server.js`**. Deploy `birdvirus-cloud` to a Node-capable host (Render, Railway, Fly.io, or a server) and add the environment variables from `.env.example` in that host's dashboard. If the frontend stays on GitHub Pages, configure its API address before deployment:

```html
<script>window.BIRDVIRUS_API_URL = "https://your-api.example.com/api/chat";</script>
```

Place that script immediately before `<script src="app.js" defer></script>` in `index.html`. The API URL is public; the API key is not.

## Local run

```bash
cd birdvirus-cloud
npm install
copy .env.example .env
# add your real key to .env
npm start
```

For the static frontend locally, serve this folder from `http://localhost:3000` or set `window.BIRDVIRUS_API_URL` to the deployed API. The server has an origin allowlist, request-size limit, input cap, and rate limit; set `ALLOWED_ORIGINS` to the exact frontend domains you use.
