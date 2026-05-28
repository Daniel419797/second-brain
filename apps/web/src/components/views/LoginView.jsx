import { Wifi } from "lucide-react";
import { API_URL } from "@/lib/config";

export function LoginView({ username, setUsername, password, setPassword, error, busy, onSubmit }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-friday-bg p-4 text-white">
      <form className="grid w-full max-w-[420px] gap-3 rounded-md border border-friday-line bg-[#111820] p-6" onSubmit={onSubmit}>
        <h1 className="m-0 text-2xl font-extrabold">Friday Command Center</h1>
        <p className="text-sm text-friday-muted">Connect to the protected local API running at {API_URL}.</p>
        <div className="grid gap-1.5">
          <label className="text-sm text-friday-muted" htmlFor="username">Username</label>
          <input className="min-h-10 rounded border border-friday-line bg-[#0b1117] px-3 text-white" id="username" value={username} onChange={(event) => setUsername(event.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm text-friday-muted" htmlFor="password">API password</label>
          <input
            className="min-h-10 rounded border border-friday-line bg-[#0b1117] px-3 text-white"
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </div>
        {error ? <p className="text-sm text-friday-danger">{error}</p> : null}
        <button className="inline-flex min-h-9 items-center justify-center gap-2 rounded border border-friday-blue bg-friday-blue px-3 py-2 font-extrabold text-[#03111f]" type="submit" disabled={busy}>
          <Wifi size={16} /> Connect
        </button>
      </form>
    </main>
  );
}
