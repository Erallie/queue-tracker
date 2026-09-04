<script lang="ts">
  import { onMount } from 'svelte';

  let { isDarkMode = $bindable() } = $props();

  onMount(() => {
    const saved = localStorage.getItem('isDarkMode');
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    isDarkMode = saved === null ? mediaQuery.matches : saved === 'true';

    const updateTheme = (event: MediaQueryListEvent) => {
      if (localStorage.getItem('isDarkMode') === null) isDarkMode = event.matches;
    };

    mediaQuery.addEventListener('change', updateTheme);
    return () => mediaQuery.removeEventListener('change', updateTheme);
  });

  function saveTheme(event: Event) {
    isDarkMode = (event.currentTarget as HTMLInputElement).checked;
    localStorage.setItem('isDarkMode', String(isDarkMode));
  }
</script>

<label class="theme-switch" title={isDarkMode ? 'Use light mode' : 'Use dark mode'}>
  <span class="sr-only">Use dark mode</span>
  <input type="checkbox" checked={isDarkMode} onchange={saveTheme} />
  <span class="track" aria-hidden="true"><span class="thumb"></span></span>
  <svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 15.2A8.5 8.5 0 0 1 8.8 3.5a8.5 8.5 0 1 0 11.7 11.7Z"/></svg>
  <svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M19.4 4.6l-2.1 2.1M6.7 17.3l-2.1 2.1"/></svg>
</label>

<style>
  .theme-switch { position: relative; display: block; width: 64px; height: 36px; color: rgb(var(--foreground)); cursor: pointer; }
  input { position: absolute; opacity: 0; pointer-events: none; }
  .track { position: absolute; inset: 0; border: 2px solid currentColor; border-radius: 999px; background: rgba(var(--background), .72); backdrop-filter: blur(8px); transition: background .3s, color .3s; }
  .thumb { position: absolute; z-index: 1; top: 4px; left: 4px; width: 24px; height: 24px; border-radius: 50%; background: currentColor; transition: transform .3s ease; }
  input:checked + .track .thumb { transform: translateX(28px); }
  input:focus-visible + .track { outline: 3px solid rgb(var(--accent)); outline-offset: 3px; }
  svg { position: absolute; z-index: 2; top: 9px; width: 18px; height: 18px; pointer-events: none; }
  .moon { left: 9px; fill: currentColor; }
  .sun { right: 9px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; }
</style>
