export function normalizeSearch(value: string): string {
  return value
    .normalize('NFKC')
    .replace(/\p{P}+/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLocaleLowerCase();
}
