<script lang="ts">
  import { base } from '$app/paths';
  import { page } from '$app/state';
  import LightDarkSwitcher from '$lib/LightDarkSwitcher.svelte';
  import logo from '$lib/assets/brand/gozar-productions-logo.svg';
  import '../app.css';

  let { children } = $props();
  let isDarkMode = $state(false);
</script>

<svelte:head>
  <meta name="description" content="Browse Erallie's song list and request a song." />
  <meta name="theme-color" content={isDarkMode ? '#17110e' : '#f8f4ee'} />
  <link rel="icon" href={`${base}/favicon.svg`} />
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
      <a class:active={page.url.pathname.startsWith(`${base}/admin`)} href={`${base}/admin`}>Dashboard</a>
    </nav>
  </header>

  <main>{@render children()}</main>

  <footer>
    <img src={logo} alt="Gozar Productions" />
    <div><strong>Gozar Productions</strong><span>Song requests for Erallie</span></div>
  </footer>
</div>
