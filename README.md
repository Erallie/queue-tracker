# Erallie Queue Tracker

A lightweight Svelte/TypeScript song-request site with a Python connector for the Raspberry Pi. The public site is static and can be hosted on GitHub Pages. The Pi connector sits behind a Cloudflare Tunnel, owns the database and OAuth callbacks, keeps a client connection to the externally hosted MustardMine queue, and records completed songs. It does not host or replace the queue.

## What is included

- Searchable public song table with AND-style tag filtering.
- New songs always first, followed by tag points, lower play count, artist/musical, and title.
- Manually configured same-song groups. Only the group display name appears; a request sends its first member.
- Twitch, Discord, and Google sign-in with account linking. Request names prefer Twitch, then Discord, then Google. Removing the final identity deletes the account.
- Play totals and last-played dates for every song.
- Owner dashboard for the source song text, same-song groups, tags and ranking points, manual play corrections, and queue settings.
- Hourly New-song eligibility checks. A song graduates only after both its play threshold and minimum age are reached.
- No generated `# New Songs` section is added to copied or editable text.

## Frontend development

1. Copy `.env.example` to `.env` and set `PUBLIC_QUEUE_API_URL` to the Pi service URL.
2. Run `npm install`.
3. Run `npm run dev`.

The frontend shows representative preview data when no API URL is set. Writes stay disabled until the owner is signed in.

## Pi connector and API

Requires Python 3.11 or newer.

1. Enter `server`, create a virtual environment, and install `requirements.txt`.
2. Copy `.env.example` to `.env` and fill in the public URL, frontend origins, OAuth credentials, owner identity IDs, and a Fernet encryption key.
3. Sign in to MustardMine in a browser as the broadcaster or a moderator for the queue. Copy the value of the `Cookie` request header (everything after `Cookie:`) from that logged-in MustardMine session into `MUSTARDMINE_COOKIE` in `.env`. Treat this value like a password. It lets the Pi submit `choose` commands with `added_for` names; without it, the public socket can read the queue but MustardMine rejects requests as `Not logged in`.
4. Run `python -m queue_tracker`.
5. Point a Cloudflare Tunnel hostname at `http://127.0.0.1:8787`. Examples for cloudflared and systemd are in `server/deploy`.

OAuth callback URLs:

- `https://YOUR_API_HOST/auth/twitch/callback`
- `https://YOUR_API_HOST/auth/discord/callback`
- `https://YOUR_API_HOST/auth/google/callback`

The session cookie is HTTP-only, Secure, and SameSite=None so it works between GitHub Pages and the API hostname. CORS is restricted to `FRONTEND_ORIGINS`.

## GitHub Pages

Set the repository Actions variable `PUBLIC_QUEUE_API_URL` to the public Cloudflare hostname, then enable GitHub Pages with **GitHub Actions** as its source. The included workflow checks, builds, and deploys the site on pushes to `main`.

## Initial data

`server/seed_songlist.md` contains the current song list. The service imports it only for a new database. The two requested same-song groups are also seeded on first launch.

## External queue protocol

The queue continues to be hosted by MustardMine. The Pi opens `wss://sikorsky.mustardmine.com/ws` as a client and sends:

```json
{"cmd":"init","type":"chan_queue","group":"#275206561"}
```

It records a play when an update shows that the previous first item shifted out and all remaining items moved forward. Song requests are sent back through that same WebSocket connection using the configured command (default `choose`), the first group member as `selection`, and the signed-in display name as `added_for`.
