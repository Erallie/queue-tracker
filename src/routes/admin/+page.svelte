<script lang="ts">
  import { onMount } from 'svelte';
  import { adjustPlay, getAdmin, getAccount, removeNewTag, saveGroups, saveSettings, saveSongTags, saveTags } from '$lib/api';
  import { tagVisualStyle } from '$lib/color';
  import { normalizeSearch } from '$lib/search';
  import { relativeTime } from '$lib/time';
  import MarkdownEditor from '$lib/MarkdownEditor.svelte';
  import type { Account, Catalog, Settings, SongGroup } from '$lib/types';

  let tab = $state<'songs' | 'groups' | 'tags' | 'tracker' | 'settings'>('songs');
  let me = $state<Account>({ authenticated: false, is_admin: false, identities: [] });
  let settings = $state<Settings>({ song_text: '', new_play_threshold: 2, new_min_days: 14, recently_graduated_days: 7, last_played_history_limit: 10, default_artist: 'Erallie', queue_websocket_url: '', queue_group: '' });
  let groups = $state<SongGroup[]>([]);
  let catalog = $state<Catalog>({ songs: [], tags: [] });
  let loading = $state(true);
  let saving = $state(false);
  let status = $state('');
  let error = $state('');
  let groupSearches = $state<Record<number, string>>({});
  let tagQuery = $state('');
  let tagFilters = $state<string[]>([]);
  let trackerQuery = $state('');
  let trackerTags = $state<string[]>([]);
  let removingNew = $state('');
  let clock = $state(Date.now());

  onMount(() => {
    const timer = window.setInterval(() => { clock = Date.now(); }, 60_000);
    return () => window.clearInterval(timer);
  });

  type GroupSongOption = {
    rawTitle: string;
    title: string;
    parenthetical: string;
    section: string;
    isNew: boolean;
  };

  function parseGroupSongOptions(text: string): GroupSongOption[] {
    const options: GroupSongOption[] = [];
    let started = false;
    let section = '';
    for (const source of text.replace(/\r\n?/g, '\n').split('\n')) {
      const line = source.trim();
      if (!started) {
        if (line.startsWith('#')) started = true;
        else continue;
      }
      if (!line || line.startsWith('*')) continue;
      if (line.startsWith('#')) {
        if (line.startsWith('# ')) section = line.slice(2).trim();
        continue;
      }
      const isNew = /\s*\[New\]\s*$/i.test(line);
      const rawTitle = line.replace(/\s*\[New\]\s*$/i, '').trim();
      const match = rawTitle.match(/^(.*?)\s*\(([^()]*)\)\s*$/);
      options.push({
        rawTitle,
        title: match?.[1]?.trim() || rawTitle,
        parenthetical: match?.[2]?.trim() || '',
        section,
        isNew
      });
    }
    return options;
  }

  const groupSongOptions = $derived(parseGroupSongOptions(settings.song_text));
  const tagColors = $derived(Object.fromEntries(catalog.tags.map((tag) => [tag.name, tag.color || '#ab212a'])));
  const tagAssignmentSongs = $derived.by(() => {
    const needle = normalizeSearch(tagQuery.trim());
    return catalog.songs.filter((song) => {
      const textMatch = !needle || normalizeSearch(`${song.title} ${song.parenthetical}`).includes(needle);
      const tagMatch = tagFilters.every((tag) => song.tags.includes(tag));
      return textMatch && tagMatch;
    });
  });
  const trackedSongs = $derived.by(() => {
    const needle = normalizeSearch(trackerQuery.trim());
    return catalog.songs.filter((song) => {
      const textMatch = !needle || normalizeSearch(`${song.title} ${song.parenthetical}`).includes(needle);
      const tagMatch = trackerTags.every((tag) => song.tags.includes(tag));
      return textMatch && tagMatch;
    }).sort((a, b) => {
      if (!a.last_played && !b.last_played) return 0;
      if (!a.last_played) return 1;
      if (!b.last_played) return -1;
      return Date.parse(b.last_played) - Date.parse(a.last_played);
    });
  });

  function cleanForCopy(text: string): string {
    const lines = text.replace(/\r\n?/g, '\n').split('\n');
    const firstHeading = lines.findIndex((line) => line.trimStart().startsWith('#'));
    if (firstHeading < 0) return '';
    const output: string[] = [];
    let skipEmptyAfterNote = false;
    for (const source of lines.slice(firstHeading)) {
      const line = source.trimEnd();
      if (line.trimStart().startsWith('*')) { skipEmptyAfterNote = true; continue; }
      if (!line && skipEmptyAfterNote) { skipEmptyAfterNote = false; continue; }
      skipEmptyAfterNote = false;
      if (line.startsWith('# ') && output.length) {
        while (output.at(-1) === '') output.pop();
        output.push('');
      }
      if (!line && (!output.length || output.at(-1) === '')) continue;
      output.push(line);
    }
    return output.join('\n').trim();
  }

  function addNewSongsSection(outputText: string, sourceText: string): string {
    const memberGroups = new Map<string, { key: string; requestTitle: string }>();
    groups.forEach((group, index) => {
      const requestTitle = group.members[0]?.replace(/\s*\[New\]\s*$/i, '').trim();
      if (!requestTitle) return;
      for (const member of group.members) {
        memberGroups.set(member, { key: group.id || `group-${index}`, requestTitle });
      }
    });

    const emittedGroups = new Set<string>();
    const newSongs: string[] = [];
    for (const song of parseGroupSongOptions(sourceText)) {
      if (!song.isNew) continue;
      const group = memberGroups.get(song.rawTitle);
      if (group) {
        if (emittedGroups.has(group.key)) continue;
        emittedGroups.add(group.key);
        newSongs.push(`${group.requestTitle} [New]`);
      } else {
        newSongs.push(`${song.rawTitle} [New]`);
      }
    }
    if (!newSongs.length) return outputText;

    const lines = outputText.replace(/\r\n?/g, '\n').split('\n');
    const firstHeading = lines.findIndex((line) => line.trimStart().startsWith('#'));
    const insertAt = firstHeading < 0 ? lines.length : firstHeading;
    const section = ['# New Songs', ...newSongs, ''];
    lines.splice(insertAt, 0, ...section);
    return lines.join('\n');
  }

  async function copyText(cleaned: boolean) {
    const text = cleaned ? cleanForCopy(settings.song_text) : settings.song_text;
    await navigator.clipboard.writeText(addNewSongsSection(text, settings.song_text));
    status = cleaned ? 'Cleaned song text copied' : 'Editable song text copied';
  }

  async function pasteText() {
    settings.song_text = await navigator.clipboard.readText();
    status = 'Clipboard text pasted. Save when it looks right.';
  }

  async function runSave(action: () => Promise<void>, message: string) {
    saving = true; status = ''; error = '';
    try { await action(); status = message; }
    catch (caught) { error = caught instanceof Error ? caught.message : 'Could not save changes'; }
    finally { saving = false; }
  }

  function addGroup() { groups = [...groups, { display_name: '', members: [] }]; }
  function addGroupMember(group: SongGroup, groupIndex: number, rawTitle: string) {
    if (!group.members.includes(rawTitle)) group.members = [...group.members, rawTitle];
    groupSearches[groupIndex] = '';
  }
  function removeGroupMember(group: SongGroup, memberIndex: number) {
    group.members = group.members.filter((_, index) => index !== memberIndex);
  }
  function groupSearchResults(group: SongGroup, groupIndex: number) {
    const query = normalizeSearch((groupSearches[groupIndex] || '').trim());
    if (!query) return [];
    const usedElsewhere = new Set(groups.flatMap((item, index) => index === groupIndex ? [] : item.members));
    return groupSongOptions.filter((song) => {
      if (group.members.includes(song.rawTitle) || usedElsewhere.has(song.rawTitle)) return false;
      return normalizeSearch(`${song.title} ${song.parenthetical} ${song.section}`).includes(query);
    }).slice(0, 12);
  }
  function addTag() { catalog.tags = [...catalog.tags, { name: 'New tag', points: 0, color: '#ab212a' }]; }
  function moveTag(tagIndex: number, direction: -1 | 1) {
    const destination = tagIndex + direction;
    if (destination < 0 || destination >= catalog.tags.length) return;
    const tags = [...catalog.tags];
    [tags[tagIndex], tags[destination]] = [tags[destination], tags[tagIndex]];
    catalog.tags = tags;
  }
  function toggleSongTag(songId: string, tag: string, checked: boolean) {
    const song = catalog.songs.find((item) => item.id === songId);
    if (!song) return;
    song.tags = checked ? [...new Set([...song.tags, tag])] : song.tags.filter((item) => item !== tag);
  }
  function toggleTrackerTag(tag: string) {
    trackerTags = trackerTags.includes(tag) ? trackerTags.filter((item) => item !== tag) : [...trackerTags, tag];
  }
  function toggleTagFilter(tag: string) {
    tagFilters = tagFilters.includes(tag) ? tagFilters.filter((item) => item !== tag) : [...tagFilters, tag];
  }
  async function manuallyRemoveNew(songId: string) {
    removingNew = songId; status = ''; error = '';
    try {
      await removeNewTag(songId);
      ({ settings, groups, catalog } = await getAdmin());
      status = 'New tag removed';
    } catch (caught) {
      error = caught instanceof Error ? caught.message : 'Could not remove the New tag';
    } finally {
      removingNew = '';
    }
  }

  onMount(async () => {
    me = await getAccount();
    if (me.is_admin) {
      try {
        ({ settings, groups, catalog } = await getAdmin());
      } catch (caught) {
        error = caught instanceof Error ? caught.message : 'Could not open the owner dashboard';
      }
    }
    loading = false;
  });
</script>

<svelte:head><title>Dashboard — Erallie's Song Queue</title></svelte:head>

<section class="page-intro"><div><div class="eyebrow">Owner dashboard</div><h1>The song desk.</h1><p class="lede">Edit the song book, group alternate versions, rank tags, and review every performance in one place.</p></div><div class="script-note" aria-hidden="true">Make it yours</div></section>

{#if loading}
  <section class="panel">Opening the dashboard…</section>
{:else}
  {#if !me.is_admin}
    <section class="panel"><h2>Owner access only</h2><p class="muted">Sign in on the Account page with Erallie's owner account to open the song-text editor, copy/paste tools, groups, tags, play history, and settings.</p></section>
  {:else}
    {#if status}<div class="notice success" role="status">{status}</div>{/if}
    {#if error}<div class="notice error" role="alert">{error}</div>{/if}

    <div class="metric-row">
    <div class="metric"><span class="muted">Songs</span><strong>{catalog.songs.length}</strong></div>
    <div class="metric"><span class="muted">New</span><strong>{catalog.songs.filter((song) => song.is_new).length}</strong></div>
    <div class="metric"><span class="muted">Groups</span><strong>{groups.length}</strong></div>
    <div class="metric"><span class="muted">Total perfor&shy;mances</span><strong>{catalog.songs.reduce((sum, song) => sum + song.play_count, 0)}</strong></div>
    </div>

    <section class="panel">
    <div class="tabs" role="tablist">
      {#each [['songs','Song list'],['groups','Song groups'],['tags','Tags & ranking'],['tracker','Play tracker'],['settings','Settings']] as item}
        <button class:active={tab === item[0]} class="tab" type="button" onclick={() => tab = item[0] as typeof tab}>{item[1]}</button>
      {/each}
    </div>

    {#if tab === 'songs'}
      <div class="section-heading"><div><h2>Editable song list</h2><p class="muted">Keep the same heading and one-song-per-line format. Adding or removing <code>[New]</code> updates tracking immediately.</p></div></div>
      <MarkdownEditor bind:value={settings.song_text} />
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => saveSettings(settings), 'Song list saved')}>Save song list</button><button class="button secondary" onclick={() => copyText(false)}>Copy exact text</button><button class="button secondary" onclick={() => copyText(true)}>Copy cleaned text</button><button class="button secondary" onclick={pasteText}>Paste from clipboard</button></div>
      <nav class="editor-destinations" aria-label="Places to update the song list">
        <span class="muted">Update the published song list:</span>
        <a class="external-inline-link" href="https://www.twitch.tv/erallie/about" target="_blank" rel="noopener noreferrer">
          <span>Twitch About</span><span class="external-nav-arrow" aria-hidden="true">&#x2197;&#xFE0E;</span>
        </a>
        <a class="external-inline-link" href="https://mustardmine.com/channels/erallie/queue" target="_blank" rel="noopener noreferrer">
          <span>MustardMine Queue</span><span class="external-nav-arrow" aria-hidden="true">&#x2197;&#xFE0E;</span>
        </a>
      </nav>
    {:else if tab === 'groups'}
      <div class="section-heading"><div><h2>Same-song groups</h2><p class="muted">Search the current song list and add the songs that should be treated as one song.</p></div><button class="button secondary small" onclick={addGroup}>Add group</button></div>
      <div class="stack">
        {#each groups as group, index}
          <div class="group-card">
            <label>Public group name<input bind:value={group.display_name} placeholder="Title (Artist or Musical)" /></label>
            <div class="member-editor">
              <span class="field-label">Group members</span>
              {#if group.members.length}
                <ul class="member-list">
                  {#each group.members as member, memberIndex}
                    <li class="member-row">
                      <span class="member-name">{member}</span>
                      <span class="member-actions">
                        <button class="remove-member" type="button" aria-label={`Remove ${member} from group`} title="Remove from group" onclick={() => removeGroupMember(group, memberIndex)}>×</button>
                      </span>
                    </li>
                  {/each}
                </ul>
              {:else}
                <p class="member-empty">No songs selected yet.</p>
              {/if}
              <div class="song-picker">
                <div class="search">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
                  <input bind:value={groupSearches[index]} type="search" placeholder="Search title, artist, or musical…" aria-label={`Search songs for group ${index + 1}`} autocomplete="off" />
                </div>
                {#if (groupSearches[index] || '').trim()}
                  {@const results = groupSearchResults(group, index)}
                  <div class="picker-results">
                    {#if results.length}
                      {#each results as song (song.rawTitle)}
                        <button class="picker-option" type="button" onclick={() => addGroupMember(group, index, song.rawTitle)}>
                          <span><strong>{song.title}</strong>{#if song.parenthetical}<small>{song.parenthetical}</small>{/if}</span>
                          <small>{song.section}</small>
                        </button>
                      {/each}
                    {:else}
                      <p class="picker-empty">No available songs match that search.</p>
                    {/if}
                  </div>
                {/if}
              </div>
              <small class="muted">A group needs at least two songs. Songs assigned to another group are hidden from the search.</small>
            </div>
            <button class="button secondary small" onclick={() => groups = groups.filter((_, i) => i !== index)}>Remove</button>
          </div>
        {/each}
      </div>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(async () => { await saveGroups(groups); ({ settings, groups, catalog } = await getAdmin()); }, 'Song groups saved')}>Save groups</button></div>
    {:else if tab === 'tags'}
      <div class="section-heading"><div><h2>Tags and ranking points</h2><p class="muted">Use the arrows to choose the order tags appear. Higher point totals rank songs first, while New songs always stay above every other song.</p></div><button class="button secondary small" onclick={addTag}>Add tag</button></div>
      <div class="stack">
        {#each catalog.tags as tag, index}
          <div class="group-card tag-editor-row">
            <label>Tag name<input bind:value={tag.name} disabled={tag.name === 'New'} /></label>
            {#if tag.name === 'New'}
              <div class="fixed-ranking"><span>Ranking points</span><strong>Always displayed first</strong></div>
            {:else}
              <label>Ranking points<input type="number" bind:value={tag.points} /></label>
            {/if}
            <div class="tag-actions">
              <input aria-label={`${tag.name} color`} title={`${tag.name} color`} type="color" bind:value={tag.color} />
              <button type="button" aria-label={`Move ${tag.name} up`} title="Move up" disabled={index === 0} onclick={() => moveTag(index, -1)}>↑</button>
              <button type="button" aria-label={`Move ${tag.name} down`} title="Move down" disabled={index === catalog.tags.length - 1} onclick={() => moveTag(index, 1)}>↓</button>
              <button class="button secondary small" disabled={tag.name === 'New'} onclick={() => catalog.tags = catalog.tags.filter((_, i) => i !== index)}>Remove</button>
            </div>
          </div>
        {/each}
      </div>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => saveTags(catalog.tags), 'Tag groups saved')}>Save tag groups</button></div>
      <h3 style="margin-top:2rem">Assign tags to songs</h3>
      <p class="muted">For a grouped song, the selected tags are applied to every member song.</p>
      <div class="toolbar">
        <div class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          <input bind:value={tagQuery} type="search" placeholder="Search title, artist, or musical…" aria-label="Search songs to assign tags" />
        </div>
        <div class="tag-list" aria-label="Filter tag assignments by tags">
          {#each catalog.tags as tag (tag.name)}
            <button class:selected={tagFilters.includes(tag.name)} class="tag-filter" style={tagVisualStyle(tag.color)} type="button" onclick={() => toggleTagFilter(tag.name)}>{tag.name}</button>
          {/each}
        </div>
      </div>
      {#if tagFilters.length > 1}<p class="muted">Showing songs that have all {tagFilters.length} selected tags.</p>{/if}
      {#if tagAssignmentSongs.length === 0}
        <div class="empty"><strong>No songs match those filters.</strong><br />Try a different search or remove a tag.</div>
      {:else}
        <div class="table-wrap tag-assignment-wrap"><table class="tag-assignment-table"><thead><tr><th>Song</th><th>Tags</th></tr></thead><tbody>
          {#each tagAssignmentSongs as song (song.id)}
            <tr><td><span class="song-title">{song.title}</span><br /><small class="muted">{song.parenthetical}</small></td><td><div class="tag-list">{#each catalog.tags.filter((item) => item.name !== 'New') as tag}<label class="tag-check" style={tagVisualStyle(tag.color)}><input type="checkbox" checked={song.tags.includes(tag.name)} onchange={(event) => toggleSongTag(song.id, tag.name, event.currentTarget.checked)} /><span>{tag.name}</span></label>{/each}</div></td></tr>
          {/each}
        </tbody></table></div>
      {/if}
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => Promise.all(catalog.songs.map((song) => saveSongTags(song.id, song.tags))).then(() => undefined), 'Song tags saved')}>Save song tags</button></div>
    {:else if tab === 'tracker'}
      <div class="section-heading"><div><h2>All songs</h2><p class="muted">Every song in the current song list appears here, whether or not it is New. Queue removals update automatically; same-song groups share one combined count.</p></div></div>
      <div class="toolbar">
        <div class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          <input bind:value={trackerQuery} type="search" placeholder="Search title, artist, or musical…" aria-label="Search tracked songs" />
        </div>
        <div class="tag-list" aria-label="Filter tracked songs by tags">
          {#each catalog.tags as tag (tag.name)}
            <button class:selected={trackerTags.includes(tag.name)} class="tag-filter" style={tagVisualStyle(tag.color)} type="button" onclick={() => toggleTrackerTag(tag.name)}>{tag.name}</button>
          {/each}
        </div>
      </div>
      {#if trackerTags.length > 1}<p class="muted">Showing songs that have all {trackerTags.length} selected tags.</p>{/if}
      {#if trackedSongs.length === 0}
        <div class="empty"><strong>No songs match those filters.</strong><br />Try a different search or remove a tag.</div>
      {:else}
        <div class="table-wrap"><table class="tracker-table"><thead><tr><th>Song</th><th>Tags</th><th>Last played</th><th class="number">Times<br />played</th><th>Adjust</th></tr></thead><tbody>
          {#each trackedSongs as song (song.id)}
            <tr>
              <td><span class="song-title">{song.title}</span><br /><small class="muted">{song.parenthetical}</small></td>
              <td><div class="tag-list">{#each song.tags as tag}<span class="tag" style={tagVisualStyle(tagColors[tag] || '#ab212a')}>{tag}</span>{/each}</div></td>
              <td>{relativeTime(song.last_played, clock)}</td>
              <td class="number">{song.play_count}</td>
              <td><div class="actions tracker-actions"><button class="button secondary small decrease-play" aria-label={`Decrease plays for ${song.title}`} onclick={async () => { const result = await adjustPlay(song.id, -1); Object.assign(song, result.song); }}>−</button><button class="button small increase-play" aria-label={`Increase plays for ${song.title}`} onclick={async () => { const result = await adjustPlay(song.id, 1); Object.assign(song, result.song); }}>+</button>{#if song.is_new}<button class="button secondary small remove-new" disabled={removingNew === song.id} onclick={() => manuallyRemoveNew(song.id)}>{removingNew === song.id ? 'Removing…' : 'Remove New'}</button>{/if}</div></td>
            </tr>
          {/each}
        </tbody></table></div>
      {/if}
    {:else}
      <div class="section-heading"><div><h2>Tracking and queue settings</h2><p class="muted">New-song eligibility is evaluated hourly by the Pi service.</p></div></div>
      <div class="form-grid">
        <label>Plays before a song graduates from New<input type="number" min="1" bind:value={settings.new_play_threshold} /></label>
        <label>Minimum days a song stays New<input type="number" min="0" bind:value={settings.new_min_days} /></label>
        <label>Days to retain recently graduated data<input type="number" min="0" bind:value={settings.recently_graduated_days} /></label>
        <label>Last-played dates retained per song<input type="number" min="1" bind:value={settings.last_played_history_limit} /></label>
        <label>Default artist for songs without parentheses<input required bind:value={settings.default_artist} /></label>
        <label>Queue group<input bind:value={settings.queue_group} /></label>
        <label class="full">Queue WebSocket URL<input type="url" bind:value={settings.queue_websocket_url} /></label>
      </div>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => saveSettings(settings), 'Settings saved')}>Save settings</button></div>
    {/if}
    </section>
  {/if}
{/if}
