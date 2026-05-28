export function Metric({ icon, label, value, sub, running }) {
  return (
    <div className="min-h-[78px] rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-3">
      <div className="flex items-center gap-2 text-xs uppercase text-friday-muted">
        {icon}
        {label}
        {typeof running === "boolean" ? (
          <span className={`h-2.5 w-2.5 rounded-full ${running ? "bg-friday-ok shadow-[0_0_16px_rgba(56,224,160,.38)]" : "bg-slate-500"}`} />
        ) : null}
      </div>
      <div className="mt-2 text-2xl font-extrabold text-white">{value}</div>
      <div className="text-xs text-friday-muted">{sub}</div>
    </div>
  );
}

export function Progress({ value = 0 }) {
  return (
    <div className="h-[7px] overflow-hidden rounded-full bg-[#2c3440]">
      <span className="block h-full bg-gradient-to-r from-[#94c8ff] to-[#f6b26b]" style={{ width: `${Number(value) || 0}%` }} />
    </div>
  );
}
