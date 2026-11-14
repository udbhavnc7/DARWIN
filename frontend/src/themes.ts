export const themes = {
  texture: {
    name: 'Green Texture', colors: 'Green on brown beige', scheme: 'light',
    page: '#e9e1cf', accent: '#2c5336', model: '#5c7a55', plate: '#cbbfa4', trace: '#48664a',
  },
  leather: {
    name: 'Leather Red', colors: 'Leather red on perfect beige', scheme: 'light',
    page: '#f2e7d4', accent: '#7c332a', model: '#a5604c', plate: '#dfcaaa', trace: '#8a4d3f',
  },
  carbon: {
    name: 'Carbon Black', colors: 'Carbon black with linen grey', scheme: 'dark',
    page: '#111311', accent: '#d9d2bf', model: '#a5a294', plate: '#2d3029', trace: '#c9c3b2',
  },
} as const;

export type ThemeId = keyof typeof themes;
export type Theme = (typeof themes)[ThemeId];
const storageKey = 'darwin-theme';

// Palettes retired in the lab-bench refresh still resolve to their nearest
// surviving neighbour, so an existing browser preference is never dropped.
const retired: Record<string, ThemeId> = {
  greenhouse: 'texture',
  terracotta: 'texture',
  rosewire: 'leather',
  hazard: 'carbon',
  ink: 'carbon',
};

export function storedTheme(value: string | null): ThemeId {
  if (value && Object.hasOwn(themes, value)) return value as ThemeId;
  if (value && Object.hasOwn(retired, value)) return retired[value];
  return 'texture';
}

export function readTheme(): ThemeId {
  try {return storedTheme(localStorage.getItem(storageKey));} catch {return 'texture';}
}

export function applyTheme(id: ThemeId) {
  const theme = themes[id];
  document.documentElement.dataset.theme = id;
  document.documentElement.style.colorScheme = theme.scheme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme.page);
}

export function saveTheme(id: ThemeId) {
  try {localStorage.setItem(storageKey, id);} catch { /* Theme still applies in this tab. */ }
}

export function onThemeStorage(event: StorageEvent, change: (id: ThemeId) => void) {
  if (event.key === storageKey || event.key === null) change(storedTheme(event.newValue));
}
