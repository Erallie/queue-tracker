const FALLBACK_TAG_COLOR = '#ab212a';

function normalizedHex(value: string | undefined): string {
  const color = value?.trim() || '';
  if (/^#[0-9a-f]{6}$/i.test(color)) return color;
  if (/^#[0-9a-f]{3}$/i.test(color)) {
    return `#${[...color.slice(1)].map((part) => `${part}${part}`).join('')}`;
  }
  return FALLBACK_TAG_COLOR;
}

export function contrastingTextColor(value: string | undefined): '#000000' | '#ffffff' {
  const color = normalizedHex(value);
  const channels = [1, 3, 5].map((start) => Number.parseInt(color.slice(start, start + 2), 16) / 255);
  const [red, green, blue] = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  );
  const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  const blackContrast = (luminance + 0.05) / 0.05;
  const whiteContrast = 1.05 / (luminance + 0.05);
  return blackContrast >= whiteContrast ? '#000000' : '#ffffff';
}

export function tagVisualStyle(value: string | undefined): string {
  const color = normalizedHex(value);
  return `--tag:${color};--tag-text:${contrastingTextColor(color)}`;
}
