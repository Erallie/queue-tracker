# Erallie Queue Tracker

A lightweight Svelte/TypeScript song-request site with a Python service for the Raspberry Pi. The public site is static and can be hosted on GitHub Pages. The Pi service sits behind a Cloudflare Tunnel and owns the database, request queue, Twitch chat listener, OBS panel, and OAuth callbacks.

## What is included

- Searchable public song table with AND-style tag filtering.
- New songs always first, followed by tag points, lower play count, artist/musical, and title.
- Manually configured same-song groups. Only the group display name appears; a request sends its first member.
- Twitch, Discord, and Google sign-in with account linking. Request names prefer Twitch, then Discord, then Google. Removing the final identity deletes the account.
- Play totals and last-played dates for every song.
- Configurable request cooldown that temporarily blocks songs performed within the chosen number of minutes.
- Owner dashboard for queue controls, the source song text, same-song groups, tags and ranking points, manual play corrections, and queue settings.
- Persistent self-hosted request queue with live website updates and an OBS-ready transparent panel.
- Twitch chat requests and removals through configurable commands.
- Optional Twitch chat announcements for new requests and queue open/close changes.
- Hourly New-song eligibility checks. A song graduates only after both its play threshold and minimum age are reached.
- No generated `# New Songs` section is added to copied or editable text.

## Frontend development

1. Copy `.env.example` to `.env` and set `PUBLIC_QUEUE_API_URL` to the Pi service URL.
2. Run `npm install`.
3. Run `npm run dev`.

The frontend shows representative preview data when no API URL is set. Writes stay disabled until the owner is signed in.

## Pi service and API

Requires Python 3.11 or newer.

1. Enter `server`, create a virtual environment, and install `requirements.txt`.
2. Copy `.env.example` to `.env` and fill in the public URL, frontend origins, OAuth credentials, owner identity IDs, and a Fernet encryption key.
3. Put the broadcaster Twitch ID in `OWNER_IDENTITIES` as `twitch:YOUR_TWITCH_ID`.
4. Run `python -m queue_tracker`.
5. Point a Cloudflare Tunnel hostname at `http://127.0.0.1:8787`. Examples for cloudflared and systemd are in `server/deploy`.
6. Sign out and back in with the owner Twitch account once after deploying. Twitch will ask for chat read/write access, which lets the service receive request commands and send enabled queue announcements. No MustardMine cookie is used.

OAuth callback URLs:

- `https://YOUR_API_HOST/auth/twitch/callback`
- `https://YOUR_API_HOST/auth/discord/callback`
- `https://YOUR_API_HOST/auth/google/callback`

The session cookie is HTTP-only, Secure, and SameSite=None so it works between GitHub Pages and the API hostname. CORS is restricted to `FRONTEND_ORIGINS`.

The default Twitch commands are `!request Song Title` and `!unchoose 2`. Both command names can be changed in the dashboard Settings tab. A title must resolve to exactly one song. A removal only succeeds when that Twitch account owns the selected queue entry.

Use `https://YOUR_API_HOST/queue?panel` as an OBS Browser Source. The panel follows the previous MustardMine panel layout and updates in place through the same live event stream as the website. When opened in a browser with the owner session, it can open or close the queue immediately, close it after a chosen number of additional requests, cancel individual requests, or complete them. OBS can display the queue without being signed in.

## GitHub Pages

Set the repository Actions variable `PUBLIC_QUEUE_API_URL` to the public Cloudflare hostname, then enable GitHub Pages with **GitHub Actions** as its source. The included workflow checks, builds, and deploys the site on pushes to `main`.

## Initial data

`server/seed_songlist.md` contains the current song list. The service imports it only for a new database. The two requested same-song groups are also seeded on first launch.

## Queue behavior

Queue entries are stored in the existing SQLite database. Website and Twitch requests feed the same list. Removing a request does not affect play history; choosing **Complete** in the owner dashboard removes it and records the performance. Opening or closing the queue is also controlled from the dashboard and updates the public site and OBS panel immediately.
