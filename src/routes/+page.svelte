<script lang="ts">
  import { base } from '$app/paths';
  import { onMount } from 'svelte';
  import { getAccount, getCatalog, requestSong } from '$lib/api';
  import type { Account, Catalog, Song } from '$lib/types';

  let catalog = $state<Catalog>({ songs: [], tags: [] });
  let account = $state<Account>({ authenticated: false, is_admin: false, identities: [] });
  let query = $state('');
  let selectedTags = $state<string[]>([]);
  let loading = $state(true);
  let requesting = $state('');
  let message = $state('');
  let error = $state('');

  const tagColors = $derived(Object.fromEntries(catalog.tags.map((tag) => [tag.name, tag.color || '#ab212a'])));
  const filtered = $derived.by(() => {
    const needle = query.trim().toLocaleLowerCase();
    return catalog.songs.filter((song) => {
      const textMatch = !needle || `${song.title} ${song.parenthetical}`.toLocaleLowerCase().includes(needle);
      const tagMatch = selectedTags.every((tag) => song.tags.includes(tag));
      return textMatch && tagMatch;
    });
  });

  function toggleTag(tag: string) {
    selectedTags = selectedTags.includes(tag) ? selectedTags.filter((item) => item !== tag) : [...selectedTags, tag];
  }

  function dateLabel(value: string | null) {
    if (!value) return 'Not yet';
    return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`));
  }

  async function queue(song: Song) {
    if (!account.authenticated) { location.href = `${base}/account`; return; }
    requesting = song.id; message = ''; error = '';
    try {
      const result = await requestSong(song.id);
      message = result.message || `${song.title} was added to the queue`;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not request this song';
    } finally { requesting = ''; }
  }

  onMount(async () => {
    [catalog, account] = await Promise.all([getCatalog(), getAccount()]);
    loading = false;
  });
</script>

<svelte:head><title>Erallie's Song Queue</title></svelte:head>

<section class="page-intro">
  <div>
    <div class="eyebrow">Live request book</div>
    <h1>What should<br />I sing next?</h1>
    <p class="lede">Browse the full song book, find a favorite, and send it straight to the request queue.</p>
  </div>
  <div class="script-note" aria-hidden="true">Pick a song ♡</div>
</section>

<section class="panel">
  <div class="toolbar">
    <div class="search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
      <input bind:value={query} type="search" placeholder="Search title, artist, or musical…" aria-label="Search songs" />
    </div>
    <div class="tag-list" aria-label="Filter by tags">
      {#each catalog.tags as tag (tag.name)}
        <button class:selected={selectedTags.includes(tag.name)} class="tag-filter" type="button" onclick={() => toggleTag(tag.name)}>{tag.name}</button>
      {/each}
    </div>
  </div>

  {#if selectedTags.length > 1}<p class="muted">Showing songs that have all {selectedTags.length} selected tags.</p>{/if}
  {#if message}<div class="notice success" role="status">{message}</div>{/if}
  {#if error}<div class="notice error" role="alert">{error}</div>{/if}

  {#if loading}
    <div class="empty">Opening the song book…</div>
  {:else if filtered.length === 0}
    <div class="empty"><strong>No songs match those filters.</strong><br />Try a different search or remove a tag.</div>
  {:else}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Title</th><th>Artist / Musical</th><th>Tags</th><th>Last played</th><th class="number">Times played</th><th><span class="sr-only">Request</span></th></tr></thead>
        <tbody>
          {#each filtered as song (song.id)}
            <tr>
              <td><div class="song-title">{song.title}</div></td>
              <td class="song-parenthetical">{song.parenthetical || 'Original'}</td>
              <td><div class="tag-list">{#each song.tags as tag}<span class="tag" style={`--tag:${tagColors[tag] || '#ab212a'}`}>{tag}</span>{/each}</div></td>
              <td>{dateLabel(song.last_played)}</td>
              <td class="number">{song.play_count}</td>
              <td class="request-cell"><button class="button small" disabled={requesting === song.id} onclick={() => queue(song)}>{requesting === song.id ? 'Sending…' : account.authenticated ? 'Request' : 'Sign in'}</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
