<script lang="ts">
  import { onMount } from 'svelte';
  import { authUrl, getAccount, logout, unlink } from '$lib/api';
  import twitchIcon from '$lib/assets/providers/twitch-glitch.svg';
  import discordIcon from '$lib/assets/providers/discord.svg';
  import googleIcon from '$lib/assets/providers/google-g.svg';
  import type { Account } from '$lib/types';

  let me = $state<Account>({ authenticated: false, is_admin: false, identities: [] });
  let loading = $state(true);
  let status = $state('');
  let error = $state('');
  const providers = [
    { id: 'twitch', name: 'Twitch', icon: twitchIcon },
    { id: 'discord', name: 'Discord', icon: discordIcon },
    { id: 'google', name: 'Google', icon: googleIcon }
  ];

  function identity(provider: string) { return me.identities.find((item) => item.provider === provider); }
  function connect(provider: string, mode: string) { location.href = authUrl(provider, mode); }

  async function disconnect(provider: string, name: string) {
    const last = me.identities.length === 1;
    if (!confirm(last ? `Disconnect ${name} and permanently delete your Queue Tracker account?` : `Disconnect ${name}?`)) return;
    try {
      const result = await unlink(provider);
      if (result.account_deleted) { me = { authenticated: false, is_admin: false, identities: [] }; status = 'Your account and saved identity were deleted.'; }
      else { me = await getAccount(); status = `${name} was disconnected.`; }
    } catch (caught) { error = caught instanceof Error ? caught.message : 'Could not disconnect account'; }
  }

  onMount(async () => { me = await getAccount(); loading = false; });
</script>

<svelte:head><title>Account — Erallie's Song Queue</title></svelte:head>

<section class="page-intro"><div><div class="eyebrow">Your account</div><h1>One profile,<br />your choice of login.</h1><p class="lede">Link Twitch, Discord, or Google. Requests use your Twitch name first, then Discord, then Google.</p></div></section>

{#if status}<div class="notice success" role="status">{status}</div>{/if}
{#if error}<div class="notice error" role="alert">{error}</div>{/if}

{#if loading}
  <section class="panel">Loading your account…</section>
{:else if !me.authenticated}
  <section class="panel">
    <div class="section-heading"><div><h2>Sign in to request</h2><p class="muted">Choose any provider. Your password is never shared with this site.</p></div></div>
    <div class="account-grid">
      {#each providers as provider}
        <button class="button secondary provider" type="button" onclick={() => connect(provider.id, 'login')}><img class="provider-mark" src={provider.icon} alt="" /><span>Continue with {provider.name}</span></button>
      {/each}
    </div>
  </section>
{:else}
  <section class="panel">
    <div class="section-heading"><div><h2>Linked accounts</h2><p class="muted">Your request name is <strong>{me.request_name}</strong>.</p></div><button class="button secondary small" onclick={async () => { await logout(); me = { authenticated: false, is_admin: false, identities: [] }; }}>Sign out</button></div>
    <div class="account-grid">
      {#each providers as provider}
        {@const linked = identity(provider.id)}
        <article class="panel account-card">
          <div class="provider"><img class="provider-mark" src={provider.icon} alt="" /><div><h3>{provider.name}</h3><span class="muted">{linked?.display_name || 'Not linked'}</span></div>{#if linked}<span class="status-dot" title="Linked"></span>{/if}</div>
          {#if linked}<button class="button secondary small" onclick={() => disconnect(provider.id, provider.name)}>Disconnect</button>{:else}<button class="button small" onclick={() => connect(provider.id, 'link')}>Link {provider.name}</button>{/if}
        </article>
      {/each}
    </div>
  </section>
{/if}
