<script lang="ts">
  import { base } from '$app/paths';
  import { onMount } from 'svelte';
  import { getAccount, getCatalog, getQueue, removeQueueItem, requestSong, watchCatalog, watchQueue } from '$lib/api';
  import { tagVisualStyle } from '$lib/color';
  import { normalizeSearch } from '$lib/search';
  import { relativeTime } from '$lib/time';
  import type { Account, Catalog, QueueState, Song } from '$lib/types';

  let catalog = $state<Catalog>({ songs: [], tags: [] });
  let account = $state<Account>({ authenticated: false, is_admin: false, identities: [] });
  let queueState = $state<QueueState>({ queue: [], connected: false, queue_open: null });
  let query = $state('');
  let selectedTags = $state<string[]>([]);
  let loading = $state(true);
  let requesting = $state('');
  let removingQueueIndex = $state<number | null>(null);
  let queueError = $state('');
  let message = $state('');
  let error = $state('');
  let clock = $state(Date.now());
  type SortField = 'title' | 'artist' | 'last_played' | 'play_count';
  type SortDirection = 'none' | 'ascending' | 'descending';
  let sortField = $state<SortField>('title');
  let sortDirection = $state<SortDirection>('none');
  let sortedSongIds = $state<string[]>([]);

  const tagColors = $derived(Object.fromEntries(catalog.tags.map((tag) => [tag.name, tag.color || '#ab212a'])));
  const filtered = $derived.by(() => {
    const needle = normalizeSearch(query.trim());
    return catalog.songs.filter((song) => {
      const textMatch = !needle || normalizeSearch(`${song.title} ${song.parenthetical}`).includes(needle);
      const tagMatch = selectedTags.every((tag) => song.tags.includes(tag));
      return textMatch && tagMatch;
    });
  });
  const displayedSongs = $derived.by(() => {
    if (sortDirection === 'none') return filtered;
    const positions = new Map(sortedSongIds.map((id, index) => [id, index]));
    return [...filtered].sort((a, b) => (positions.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (positions.get(b.id) ?? Number.MAX_SAFE_INTEGER));
  });

  function alphabeticalKey(value: string): string {
    return value.trim().replace(/^(?:a|an|the)\s+/i, '');
  }

  function compareText(a: string, b: string): number {
    const primary = alphabeticalKey(a).localeCompare(alphabeticalKey(b), undefined, { numeric: true, sensitivity: 'base' });
    return primary || a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
  }

  function compareSongs(a: Song, b: Song, field: SortField): number {
    if (field === 'title') return compareText(a.title, b.title);
    if (field === 'artist') return compareText(a.parenthetical, b.parenthetical) || compareText(a.title, b.title);
    if (field === 'play_count') return a.play_count - b.play_count;
    if (!a.last_played && !b.last_played) return 0;
    if (!a.last_played) return -1;
    if (!b.last_played) return 1;
    return Date.parse(a.last_played) - Date.parse(b.last_played);
  }

  function setSort(field: SortField, direction: SortDirection) {
    sortField = field;
    sortDirection = direction;
    if (direction === 'none') {
      sortedSongIds = [];
      return;
    }
    const originalPositions = new Map(catalog.songs.map((song, index) => [song.id, index]));
    const multiplier = direction === 'ascending' ? 1 : -1;
    sortedSongIds = [...catalog.songs]
      .sort((a, b) => (compareSongs(a, b, field) * multiplier) || ((originalPositions.get(a.id) ?? 0) - (originalPositions.get(b.id) ?? 0)))
      .map((song) => song.id);
  }

  function cycleSort(field: SortField) {
    const nextDirection: SortDirection = sortField !== field || sortDirection === 'none'
      ? 'ascending'
      : sortDirection === 'ascending'
        ? 'descending'
        : 'none';
    setSort(field, nextDirection);
  }

  function selectSortField(event: Event) {
    setSort((event.currentTarget as HTMLSelectElement).value as SortField, sortDirection === 'none' ? 'ascending' : sortDirection);
  }

  function sortMarker(field: SortField): string {
    if (sortField !== field || sortDirection === 'none') return '';
    return sortDirection === 'ascending' ? '↑' : '↓';
  }

  function toggleTag(tag: string) {
    selectedTags = selectedTags.includes(tag) ? selectedTags.filter((item) => item !== tag) : [...selectedTags, tag];
  }

  function applyLiveCatalog(next: Catalog) {
    if (catalog.songs.length === 0) {
      catalog = next;
      return;
    }
    const updates = new Map(next.songs.map((song) => [song.id, song]));
    const existingIds = new Set(catalog.songs.map((song) => song.id));
    catalog = {
      tags: next.tags,
      songs: [
        ...catalog.songs.flatMap((song) => updates.has(song.id) ? [updates.get(song.id)!] : []),
        ...next.songs.filter((song) => !existingIds.has(song.id))
      ]
    };
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

  async function removeFromQueue(index: number, title: string) {
    if (!confirm(`Remove ${title} from the queue?`)) return;
    removingQueueIndex = index;
    queueError = '';
    try {
      await removeQueueItem(index);
    } catch (caught) {
      queueError = caught instanceof Error ? caught.message : 'Could not remove this request';
    } finally {
      removingQueueIndex = null;
    }
  }

  onMount(() => {
    let alive = true;
    let receivedLiveQueue = false;
    let receivedLiveCatalog = false;
    const clockTimer = window.setInterval(() => { clock = Date.now(); }, 60_000);
    const stopWatchingCatalog = watchCatalog((next) => {
      receivedLiveCatalog = true;
      applyLiveCatalog(next);
    });
    const stopWatching = watchQueue((next) => {
      receivedLiveQueue = true;
      queueState = next;
    });
    void Promise.all([getCatalog(), getAccount()]).then(([nextCatalog, nextAccount]) => {
      if (!alive) return;
      if (!receivedLiveCatalog) catalog = nextCatalog;
      account = nextAccount;
      loading = false;
    });
    void getQueue().then((initialQueue) => {
      if (alive && !receivedLiveQueue) queueState = initialQueue;
    });
    return () => {
      alive = false;
      window.clearInterval(clockTimer);
      stopWatchingCatalog();
      stopWatching();
    };
  });
</script>

<svelte:head>
    <title>Erallie's Song Queue</title>
</svelte:head>

<section class="page-intro">
  <div>
    <div class="eyebrow">Live request book</div>
    <h1>What should<br />I sing next?</h1>
    <p class="lede">Browse the full song book, find a favorite, and send it straight to the request queue.</p>
  </div>
  <div class="script-note" aria-hidden="true">Pick a song ♡</div>
</section>

<section class="panel queue-panel" aria-labelledby="current-queue-heading" aria-live="polite">
  <div class="section-heading queue-heading">
    <div>
      <div class="eyebrow">Live queue</div>
      <h2 id="current-queue-heading">Up next</h2>
    </div>
    <span class:open={queueState.queue_open === true} class:closed={queueState.queue_open === false} class="queue-status">
      {queueState.queue_open === null ? 'Checking queue' : queueState.queue_open ? 'Queue open' : 'Queue closed'}
    </span>
  </div>
  <div class="queue-viewport">
    {#if queueError}<div class="notice error" role="alert">{queueError}</div>{/if}
    {#if queueState.queue.length === 0}
      <p class="queue-empty">The request queue is empty.</p>
    {:else}
      <ol class="queue-list">
        {#each queueState.queue as item, index (`${index}-${item.title}-${item.user}`)}
          <li class:owned={item.can_remove}>
            <span class="queue-position">{index + 1}</span>
            <span class="queue-song"><strong>{item.title}</strong>{#if item.user}<small>Requested by {item.user}</small>{/if}</span>
            {#if item.can_remove}<button class="button secondary small queue-remove" disabled={removingQueueIndex === index} onclick={() => removeFromQueue(index, item.title)}>{removingQueueIndex === index ? 'Removing…' : 'Remove'}</button>{/if}
          </li>
        {/each}
      </ol>
    {/if}
  </div>
</section>

<section class="panel">
  <div class="toolbar">
    <div class="search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
      <input bind:value={query} type="search" placeholder="Search title, artist, or musical…" aria-label="Search songs" />
    </div>
    <div class="tag-list" aria-label="Filter by tags">
      {#each catalog.tags as tag (tag.name)}
        <button class:selected={selectedTags.includes(tag.name)} class="tag-filter" style={tagVisualStyle(tag.color)} type="button" onclick={() => toggleTag(tag.name)}>{tag.name}</button>
      {/each}
    </div>
  </div>

  {#if selectedTags.length > 1}<p class="muted">Showing songs that have all {selectedTags.length} selected tags.</p>{/if}
  {#if message}<div class="notice success" role="status">{message}</div>{/if}
  {#if error}<div class="notice error" role="alert">{error}</div>{/if}

  <div class="mobile-sort-controls">
    <label for="mobile-sort-field">Sort by</label>
    <select id="mobile-sort-field" value={sortField} onchange={selectSortField}>
      <option value="title">Title</option>
      <option value="artist">Artist / Musical</option>
      <option value="last_played">Last played</option>
      <option value="play_count">Times played</option>
    </select>
    <button class="button secondary sort-direction" type="button" onclick={() => cycleSort(sortField)} aria-label={`Current direction: ${sortDirection}. Change sort direction.`}>
      {sortDirection === 'none' ? 'Not sorted' : sortDirection === 'ascending' ? 'Ascending ↑' : 'Descending ↓'}
    </button>
  </div>

  {#if loading}
    <div class="empty">Opening the song book…</div>
  {:else if displayedSongs.length === 0}
    <div class="empty"><strong>No songs match those filters.</strong><br />Try a different search or remove a tag.</div>
  {:else}
    <div class="table-wrap song-table-wrap">
      <table class="song-table">
        <thead><tr>
          <th class="sortable" aria-sort={sortField === 'title' ? sortDirection : 'none'}><button type="button" onclick={() => cycleSort('title')}>Title <span aria-hidden="true">{sortMarker('title')}</span></button></th>
          <th class="sortable" aria-sort={sortField === 'artist' ? sortDirection : 'none'}><button type="button" onclick={() => cycleSort('artist')}>Artist / Musical <span aria-hidden="true">{sortMarker('artist')}</span></button></th>
          <th>Tags</th>
          <th class="sortable" aria-sort={sortField === 'last_played' ? sortDirection : 'none'}><button type="button" onclick={() => cycleSort('last_played')}>Last played <span aria-hidden="true">{sortMarker('last_played')}</span></button></th>
          <th class="number sortable" aria-sort={sortField === 'play_count' ? sortDirection : 'none'}><button type="button" onclick={() => cycleSort('play_count')}>Times played <span aria-hidden="true">{sortMarker('play_count')}</span></button></th>
          <th><span class="sr-only">Request</span></th>
        </tr></thead>
        <tbody>
          {#each displayedSongs as song (song.id)}
            <tr>
              <td class="song-name-cell">
                <div class="song-title">{song.title}</div>
                <div class="mobile-song-parenthetical">{song.parenthetical}</div>
              </td>
              <td class="song-parenthetical desktop-song-parenthetical">{song.parenthetical}</td>
              <td class="song-tags-cell"><div class="tag-list">{#each song.tags as tag}<span class="tag" style={tagVisualStyle(tagColors[tag] || '#ab212a')}>{tag}</span>{/each}</div></td>
              <td class="song-last-played">{relativeTime(song.last_played, clock)}</td>
              <td class="number song-play-count">{song.play_count}</td>
              <td class="request-cell"><button class="button small" disabled={requesting === song.id} onclick={() => queue(song)}>{requesting === song.id ? 'Sending…' : account.authenticated ? 'Request' : 'Sign in'}</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
