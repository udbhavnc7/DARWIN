export const themes = {
  texture: {
    name: 'Green Texture', colors: 'Laboratory green on clean white', scheme: 'light',
    page: '#f2f7f1', accent: '#1e6a3b', model: '#4f9466', plate: '#cfe2cc', trace: '#2c7a48',
  },
  leather: {
    name: 'Leather Red', colors: 'Oxblood leather on perfect beige', scheme: 'light',
    page: '#f4ebdc', accent: '#8a2a22', model: '#a95c48', plate: '#e0cdae', trace: '#8f4a3c',
  },
  carbon: {
    name: 'Carbon Black', colors: 'Graphite with linen grey', scheme: 'dark',
    page: '#0f1110', accent: '#ddd7c7', model: '#a7a497', plate: '#2c302b', trace: '#cbc5b4',
  },
  blueprint: {
    name: 'Blueprint', colors: 'Cobalt drafting ink on cool white', scheme: 'light',
    page: '#eef3fa', accent: '#1d4f91', model: '#4d78b4', plate: '#cdd9ec', trace: '#2d60a6',
  },
  amethyst: {
    name: 'Amethyst', colors: 'Violet specimen stain on lilac white', scheme: 'light',
    page: '#f4f1f8', accent: '#5b3a8c', model: '#8869b6', plate: '#ddd3ea', trace: '#6c49a2',
  },
  midnight: {
    name: 'Midnight', colors: 'Signal blue on deep navy', scheme: 'dark',
    page: '#0c1220', accent: '#8fb4ff', model: '#6d8dc6', plate: '#1e293e', trace: '#a6c1ff',
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
