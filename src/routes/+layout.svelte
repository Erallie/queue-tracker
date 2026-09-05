<script lang="ts">
  import { base } from '$app/paths';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import { accountChangedEvent, getAccount } from '$lib/api';
  import LightDarkSwitcher from '$lib/LightDarkSwitcher.svelte';
  import logo from '$lib/assets/brand/gozar-productions-logo.svg';
  import type { Account } from '$lib/types';
  import '../app.css';

  let { children } = $props();
  let isDarkMode = $state(false);
  let account = $state<Account>({ authenticated: false, is_admin: false, identities: [] });

  onMount(() => {
    let active = true;
    const refreshAccount = async () => {
      const next = await getAccount();
      if (active) account = next;
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void refreshAccount();
    };
    void refreshAccount();
    window.addEventListener(accountChangedEvent, refreshAccount);
    window.addEventListener('focus', refreshAccount);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      active = false;
      window.removeEventListener(accountChangedEvent, refreshAccount);
      window.removeEventListener('focus', refreshAccount);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  });
</script>

<svelte:head>
  <meta name="description" content="Browse Erallie's song list and request a song." />
  <meta name="theme-color" content={isDarkMode ? '#17110e' : '#f8f4ee'} />
  <link rel="icon" type="image/png" href={`${base}/favicon.png`} />
</svelte:head>

<div class:dark={isDarkMode} class:light={!isDarkMode} class="app-shell">
  <div class="background-image" aria-hidden="true"></div>

  <header class="site-header">
    <LightDarkSwitcher bind:isDarkMode />
    <a class="brand" href={`${base}/`} aria-label="Erallie's song list home">
      <img src={logo} alt="" />
      <span>
        <span class="brand-script">Erallie</span>
        <span class="brand-title">Song List</span>
      </span>
    </a>
    <nav aria-label="Main navigation">
      <a class:active={page.url.pathname === `${base}/`} href={`${base}/`}>Songs</a>
      <a class:active={page.url.pathname.startsWith(`${base}/account`)} href={`${base}/account`}>Account</a>
      {#if account.authenticated && account.is_admin}
        <a class:active={page.url.pathname.startsWith(`${base}/admin`)} href={`${base}/admin`}>Dashboard</a>
      {/if}
      <a href="https://GozarProductions.com" rel="external">Back &#x2197;&#xFE0E;</a>
    </nav>
  </header>

  <main>{@render children()}</main>

  <footer>
    <img src={logo} alt="Gozar Productions" />
    <div><strong>Gozar Productions</strong><span>Song requests for Erallie</span></div>
  </footer>
</div>
