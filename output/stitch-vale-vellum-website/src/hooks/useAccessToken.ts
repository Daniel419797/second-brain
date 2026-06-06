'use client';

import { useCallback, useState } from 'react';
import { clearAccessToken, readAccessToken, writeAccessToken } from '@/lib/authTokens';

export function useAccessToken() {
  const [token, setCurrentToken] = useState(readAccessToken);

  const setToken = useCallback((value: string) => {
    writeAccessToken(value);
    setCurrentToken(value);
  }, []);

  const clearToken = useCallback(() => {
    clearAccessToken();
    setCurrentToken('');
  }, []);

  return { token, setToken, clearToken };
}
