<script lang="ts">
  import { base } from '$app/paths';
  import { page } from '$app/state';
  import logo from '$lib/assets/brand/gozar-productions-logo.svg';
  import '../app.css';
  let { children } = $props();
</script>

<svelte:head>
  <meta name="description" content="Browse Erallie's song list and request a song." />
  <link rel="icon" href={`${base}/favicon.svg`} />
</svelte:head>

<header class="site-header">
  <a class="brand" href={`${base}/`} aria-label="Erallie's song queue home">
    <span class="brand-script">Erallie</span>
    <span class="brand-title">Song Queue</span>
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
  <span>Gozar Productions</span>
  <span aria-hidden="true">✦</span>
  <span>Song requests for Erallie</span>
</footer>
