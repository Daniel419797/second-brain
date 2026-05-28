"use client";

import { useCallback, useEffect, useState } from "react";
import { loginToFriday } from "@/services/fridayApi";

const TOKEN_KEY = "friday_token";

export function useFridaySession() {
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("friday");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setToken(window.localStorage.getItem(TOKEN_KEY) || "");
  }, []);

  async function login(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await loginToFriday({ username, password });
      window.localStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setPassword("");
  }, []);

  return {
    token,
    username,
    setUsername,
    password,
    setPassword,
    busy,
    error,
    setError,
    login,
    logout
  };
}
