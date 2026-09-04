<script lang="ts">
  import { onMount } from 'svelte';
  import { adjustPlay, getAdmin, getAccount, saveGroups, saveSettings, saveSongTags, saveTags } from '$lib/api';
  import type { Account, Catalog, Settings, SongGroup } from '$lib/types';

  let tab = $state<'songs' | 'groups' | 'tags' | 'tracker' | 'settings'>('songs');
  let me = $state<Account>({ authenticated: false, is_admin: false, identities: [] });
  let settings = $state<Settings>({ song_text: '', new_play_threshold: 2, new_min_days: 14, recently_graduated_days: 7, queue_websocket_url: '', queue_group: '', request_command: 'choose' });
  let groups = $state<SongGroup[]>([]);
  let catalog = $state<Catalog>({ songs: [], tags: [] });
  let loading = $state(true);
  let saving = $state(false);
  let status = $state('');
  let error = $state('');

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

  async function copyText(cleaned: boolean) {
    await navigator.clipboard.writeText(cleaned ? cleanForCopy(settings.song_text) : settings.song_text);
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

  function addGroup() { groups = [...groups, { display_name: '', members: ['', ''] }]; }
  function setMembers(group: SongGroup, value: string) { group.members = value.split('\n').map((line) => line.trim()).filter(Boolean); }
  function addTag() { catalog.tags = [...catalog.tags, { name: 'New tag', points: 0, color: '#ab212a' }]; }
  function toggleSongTag(songId: string, tag: string, checked: boolean) {
    const song = catalog.songs.find((item) => item.id === songId);
    if (!song) return;
    song.tags = checked ? [...new Set([...song.tags, tag])] : song.tags.filter((item) => item !== tag);
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
    <div class="metric"><span class="muted">Total performances</span><strong>{catalog.songs.reduce((sum, song) => sum + song.play_count, 0)}</strong></div>
    </div>

    <section class="panel">
    <div class="tabs" role="tablist">
      {#each [['songs','Song list'],['groups','Song groups'],['tags','Tags & ranking'],['tracker','Play tracker'],['settings','Settings']] as item}
        <button class:active={tab === item[0]} class="tab" type="button" onclick={() => tab = item[0] as typeof tab}>{item[1]}</button>
      {/each}
    </div>

    {#if tab === 'songs'}
      <div class="section-heading"><div><h2>Editable song list</h2><p class="muted">Keep the same heading and one-song-per-line format. Adding or removing <code>[New]</code> updates tracking immediately.</p></div></div>
      <textarea class="song-editor" bind:value={settings.song_text} spellcheck="false" aria-label="Song list"></textarea>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => saveSettings(settings), 'Song list saved')}>Save song list</button><button class="button secondary" onclick={() => copyText(false)}>Copy exact text</button><button class="button secondary" onclick={() => copyText(true)}>Copy cleaned text</button><button class="button secondary" onclick={pasteText}>Paste from clipboard</button></div>
    {:else if tab === 'groups'}
      <div class="section-heading"><div><h2>Same-song groups</h2><p class="muted">The display name supplies the public title and parenthetical. Requests send the first member.</p></div><button class="button secondary small" onclick={addGroup}>Add group</button></div>
      <div class="stack">
        {#each groups as group, index}
          <div class="group-card">
            <label>Public group name<input bind:value={group.display_name} placeholder="Title (Artist or Musical)" /></label>
            <label>Members, first one requested<textarea value={group.members.join('\n')} oninput={(event) => setMembers(group, event.currentTarget.value)} rows="4"></textarea></label>
            <button class="button secondary small" onclick={() => groups = groups.filter((_, i) => i !== index)}>Remove</button>
          </div>
        {/each}
      </div>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => saveGroups(groups), 'Song groups saved')}>Save groups</button></div>
    {:else if tab === 'tags'}
      <div class="section-heading"><div><h2>Tags and ranking points</h2><p class="muted">Higher tag totals appear first. New songs always stay above every other song.</p></div><button class="button secondary small" onclick={addTag}>Add tag</button></div>
      <div class="stack">
        {#each catalog.tags as tag, index}
          <div class="group-card"><label>Tag name<input bind:value={tag.name} disabled={tag.name === 'New'} /></label><label>Ranking points<input type="number" bind:value={tag.points} /></label><div class="actions"><input aria-label={`${tag.name} color`} type="color" bind:value={tag.color} style="width:46px;padding:.2rem" /><button class="button secondary small" disabled={tag.name === 'New'} onclick={() => catalog.tags = catalog.tags.filter((_, i) => i !== index)}>Remove</button></div></div>
        {/each}
      </div>
      <h3 style="margin-top:2rem">Assign tags to songs</h3>
      <p class="muted">A grouped song applies the selected tags to the version used for requests.</p>
      <div class="table-wrap"><table><thead><tr><th>Song</th><th>Tags</th></tr></thead><tbody>
        {#each catalog.songs as song}
          <tr><td><span class="song-title">{song.title}</span><br /><small class="muted">{song.parenthetical}</small></td><td><div class="tag-list">{#each catalog.tags.filter((item) => item.name !== 'New') as tag}<label class="tag-check"><input type="checkbox" checked={song.tags.includes(tag.name)} onchange={(event) => toggleSongTag(song.id, tag.name, event.currentTarget.checked)} /><span>{tag.name}</span></label>{/each}</div></td></tr>
        {/each}
      </tbody></table></div>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(async () => { await saveTags(catalog.tags); await Promise.all(catalog.songs.map((song) => saveSongTags(song.id, song.tags))); }, 'Tags and song assignments saved')}>Save tags</button></div>
    {:else if tab === 'tracker'}
      <div class="section-heading"><div><h2>All songs</h2><p class="muted">Every song in the current song list appears here, whether or not it is New. Queue removals update automatically; same-song groups share one combined count.</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>Song</th><th>Last played</th><th class="number">Times played</th><th>Adjust</th></tr></thead><tbody>
        {#each catalog.songs as song}
          <tr><td><span class="song-title">{song.title}</span><br /><small class="muted">{song.parenthetical}</small></td><td>{song.last_played || 'Not yet'}</td><td class="number">{song.play_count}</td><td><div class="actions"><button class="button secondary small" onclick={async () => { await adjustPlay(song.id, -1); song.play_count = Math.max(0, song.play_count - 1); }}>−</button><button class="button small" onclick={async () => { await adjustPlay(song.id, 1); song.play_count += 1; }}>+</button></div></td></tr>
        {/each}
      </tbody></table></div>
    {:else}
      <div class="section-heading"><div><h2>Tracking and queue settings</h2><p class="muted">New-song eligibility is evaluated hourly by the Pi service.</p></div></div>
      <div class="form-grid">
        <label>Plays before a song graduates from New<input type="number" min="1" bind:value={settings.new_play_threshold} /></label>
        <label>Minimum days a song stays New<input type="number" min="0" bind:value={settings.new_min_days} /></label>
        <label>Days to retain recently graduated data<input type="number" min="0" bind:value={settings.recently_graduated_days} /></label>
        <label>Queue group<input bind:value={settings.queue_group} /></label>
        <label class="full">Queue WebSocket URL<input type="url" bind:value={settings.queue_websocket_url} /></label>
        <label>Request command<input bind:value={settings.request_command} /></label>
      </div>
      <div class="actions"><button class="button green" disabled={saving} onclick={() => runSave(() => saveSettings(settings), 'Settings saved')}>Save settings</button></div>
    {/if}
    </section>
  {/if}
{/if}
