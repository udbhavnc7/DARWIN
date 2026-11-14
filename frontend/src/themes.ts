export const themes = {
  greenhouse: {name: 'Greenhouse', colors: 'White & green', scheme: 'light', page: '#f3f7f2', accent: '#176541', model: '#399767', plate: '#dce9dc', trace: '#36604a'},
  hazard: {name: 'Hazard', colors: 'Black & yellow', scheme: 'dark', page: '#151410', accent: '#f7d74d', model: '#ebbb29', plate: '#3d3723', trace: '#f4d769'},
  rosewire: {name: 'Rosewire', colors: 'Red & pink', scheme: 'light', page: '#fdf0f2', accent: '#a41f44', model: '#ce4469', plate: '#f4bdc9', trace: '#a13151'},
  terracotta: {name: 'Terracotta', colors: 'Brown & beige', scheme: 'light', page: '#f4eadc', accent: '#744525', model: '#a16038', plate: '#dfc3a6', trace: '#795438'},
  ink: {name: 'Ink & Paper', colors: 'White & black', scheme: 'light', page: '#f4f4f2', accent: '#222222', model: '#4f4f4f', plate: '#d4d4d1', trace: '#555555'},
} as const;

export type ThemeId = keyof typeof themes;
export type Theme = (typeof themes)[ThemeId];
const storageKey = 'darwin-theme';

export function storedTheme(value: string | null): ThemeId {
  return value && Object.hasOwn(themes, value) ? value as ThemeId : 'greenhouse';
}

export function readTheme(): ThemeId {
  try {return storedTheme(localStorage.getItem(storageKey));} catch {return 'greenhouse';}
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
