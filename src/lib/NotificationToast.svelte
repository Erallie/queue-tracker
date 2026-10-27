<script lang="ts">
  let {
    message,
    kind = 'success',
    ondismiss
  }: {
    message: string;
    kind?: 'success' | 'error';
    ondismiss: () => void;
  } = $props();
</script>

<div class:success={kind === 'success'} class:error={kind === 'error'} class="notice notification-toast" role={kind === 'error' ? 'alert' : 'status'} aria-atomic="true">
  <span>{message}</span>
  <button class="toast-dismiss" type="button" aria-label="Dismiss notification" onclick={ondismiss}>
    <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
  </button>
</div>
