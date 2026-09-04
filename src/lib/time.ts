export function relativeTime(value: string | null, currentTime = Date.now()): string {
  if (!value) return 'Never';
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return 'Never';

  const minutes = Math.max(0, currentTime - timestamp) / 60_000;
  if (minutes < 1) return 'Less than a minute ago';

  const units = minutes < 60
    ? { value: minutes, name: 'minute' }
    : minutes < 60 * 24
      ? { value: minutes / 60, name: 'hour' }
      : minutes < 60 * 24 * 7
        ? { value: minutes / (60 * 24), name: 'day' }
        : minutes < 60 * 24 * 30.4375
          ? { value: minutes / (60 * 24 * 7), name: 'week' }
          : minutes < 60 * 24 * 365.25
            ? { value: minutes / (60 * 24 * 30.4375), name: 'month' }
            : { value: minutes / (60 * 24 * 365.25), name: 'year' };

  const rounded = Math.round(units.value * 10) / 10;
  const amount = Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1);
  return `${amount} ${units.name}${rounded === 1 ? '' : 's'} ago`;
}
