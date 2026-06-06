const ACCESS_TOKEN_KEY = 'friday.access-token';

export function readAccessToken() {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(ACCESS_TOKEN_KEY) ?? '';
}

export function writeAccessToken(value: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, value);
}

export function clearAccessToken() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}
