"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Brain,
  CheckCircle2,
  ChevronRight,
  Database,
  Edit3,
  Flag,
  Folder,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Trash2,
  User,
  Users,
  Zap
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const REVIEW_LIMIT = 50;

export function MemoryView() {
  const { api, data, refresh } = useDashboard();
  const [reviews, setReviews] = useState([]);
  const [projectMemory, setProjectMemory] = useState(null);
  const [knowledgeGraph, setKnowledgeGraph] = useState(null);
  const [privateMemory, setPrivateMemory] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState("");
  const [status, setStatus] = useState("");

  const loadMemory = useCallback(async () => {
    setLoading(true);
    setStatus("");
    const [reviewResult, projectResult, graphResult, privateResult] = await Promise.allSettled([
      api(`/memory-review/items?status=pending&limit=${REVIEW_LIMIT}`),
      api("/project-memory/status"),
      api("/knowledge-graph/summary"),
      api("/private-memory/summary")
    ]);
    if (reviewResult.status === "fulfilled") setReviews(Array.isArray(reviewResult.value) ? reviewResult.value : []);
    if (projectResult.status === "fulfilled") setProjectMemory(projectResult.value);
    if (graphResult.status === "fulfilled") setKnowledgeGraph(graphResult.value);
    if (privateResult.status === "fulfilled") setPrivateMemory(privateResult.value);
    const firstError = [reviewResult, projectResult, graphResult, privateResult].find((result) => result.status === "rejected");
    if (firstError) setStatus(firstError.reason?.message || "Some memory data could not be loaded.");
    setLoading(false);
  }, [api]);

  useEffect(() => {
    loadMemory();
  }, [loadMemory]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const allSelected = reviews.length > 0 && selectedIds.length === reviews.length;
  const projects = projectMemory?.projects || data.projectMemory?.projects || data.projects || [];
  const knowledgeTiles = useMemo(
    () => buildKnowledgeTiles({ projects, knowledgeGraph, privateMemory, reviews, data }),
    [data, knowledgeGraph, privateMemory, projects, reviews]
  );

  async function scanQueue() {
    setActionBusy("scan");
    setStatus("");
    try {
      const result = await api("/memory-review/generate", { method: "POST", body: JSON.stringify({}) });
      setStatus(result.summary || "Memory review queue refreshed.");
      await loadMemory();
      await refresh();
    } catch (err) {
      setStatus(err.message || "Memory scan failed.");
    } finally {
      setActionBusy("");
    }
  }

  async function resolveReview(reviewId, decision) {
    setActionBusy(`${decision}:${reviewId}`);
    setStatus("");
    try {
      await api(`/memory-review/items/${reviewId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ decision, note: "Resolved from Memory dashboard." })
      });
      setReviews((items) => items.filter((item) => Number(item.id) !== Number(reviewId)));
      setSelectedIds((ids) => ids.filter((id) => Number(id) !== Number(reviewId)));
      setStatus(memoryDecisionText(decision));
      await refresh();
    } catch (err) {
      setStatus(err.message || "Memory update failed.");
    } finally {
      setActionBusy("");
    }
  }

  async function resolveSelected(decision) {
    if (!selectedIds.length) return;
    setActionBusy(`selected:${decision}`);
    setStatus("");
    try {
      await Promise.all(
        selectedIds.map((reviewId) =>
          api(`/memory-review/items/${reviewId}/resolve`, {
            method: "POST",
            body: JSON.stringify({ decision, note: "Resolved from Memory dashboard selection." })
          })
        )
      );
      const resolved = new Set(selectedIds.map(Number));
      setReviews((items) => items.filter((item) => !resolved.has(Number(item.id))));
      setSelectedIds([]);
      setStatus(`${resolved.size} memory review item(s) resolved.`);
      await refresh();
    } catch (err) {
      setStatus(err.message || "Selected memory update failed.");
    } finally {
      setActionBusy("");
    }
  }

  function toggleSelect(reviewId) {
    setSelectedIds((ids) => (ids.includes(reviewId) ? ids.filter((id) => id !== reviewId) : [...ids, reviewId]));
  }

  function toggleSelectAll() {
    setSelectedIds(allSelected ? [] : reviews.map((item) => item.id));
  }

  return (
    <section className="min-h-full bg-friday-bg text-[#eaf2fb]" aria-label="Memory knowledge engine">
      <div className="grid min-w-0 gap-3 xl:grid-cols-[310px_minmax(0,1fr)]">
        <aside className="grid min-w-0 content-start gap-3">
          <KnowledgeEngine tiles={knowledgeTiles} />
          <MemoryConstitution privateMemory={privateMemory} />
        </aside>

        <main className="grid min-w-0 content-start gap-3">
          <header className="flex min-h-[54px] min-w-0 items-start gap-3">
            <div className="min-w-0">
              <h2 className="m-0 text-[22px] font-extrabold tracking-normal text-white">Review Queue</h2>
              <p className="mt-1 text-[13px] leading-snug text-[#c5d0de]">
                Validate {reviews.length} pending knowledge acquisition{reviews.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-2">
              {selectedIds.length ? (
                <button
                  className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-[#315c48] bg-[#12251f] px-3 font-mono text-[11px] font-bold text-[#8df0c6] transition-colors hover:border-[#8df0c6] disabled:opacity-50"
                  type="button"
                  onClick={() => resolveSelected("keep")}
                  disabled={Boolean(actionBusy)}
                >
                  <CheckCircle2 size={14} />
                  Keep {selectedIds.length}
                </button>
              ) : null}
              <button
                className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-friday-line bg-[#10161d] px-3 font-mono text-[11px] font-bold text-[#dfe9f6] transition-colors hover:border-friday-accent disabled:opacity-50"
                type="button"
                onClick={toggleSelectAll}
                disabled={!reviews.length || Boolean(actionBusy)}
              >
                <ShieldCheck size={14} />
                {allSelected ? "Clear" : "Select All"}
              </button>
              <button
                className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-[#44607e] bg-[#172334] px-3 font-mono text-[11px] font-bold text-friday-accent transition-colors hover:border-friday-accent disabled:opacity-50"
                type="button"
                onClick={scanQueue}
                disabled={Boolean(actionBusy)}
              >
                {actionBusy === "scan" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                Scan Queue
              </button>
            </div>
          </header>

          <div className="grid min-w-0 gap-3">
            {loading ? (
              <EmptyQueue icon={<Loader2 className="animate-spin" size={18} />} title="Loading memory review queue" detail="Checking pending review items and memory indexes." />
            ) : reviews.length ? (
              reviews.map((review) => (
                <ReviewCard
                  key={review.id}
                  review={review}
                  selected={selectedSet.has(review.id)}
                  busy={actionBusy}
                  onSelect={() => toggleSelect(review.id)}
                  onResolve={resolveReview}
                />
              ))
            ) : (
              <EmptyQueue
                icon={<Brain size={18} />}
                title="No pending memory review items"
                detail="Run a queue scan to create review prompts from saved personal memories and relationship facts."
                actionLabel="Scan Memory"
                busy={actionBusy === "scan"}
                onAction={scanQueue}
              />
            )}
          </div>

          {status ? (
            <div className="fixed bottom-5 right-5 z-20 max-w-[360px] rounded-[4px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">
              {status}
            </div>
          ) : null}
        </main>
      </div>
    </section>
  );
}

function KnowledgeEngine({ tiles }) {
  return (
    <Panel className="p-3">
      <PanelTitle title="Knowledge Engine" />
      <div className="mt-3 grid gap-2">
        {tiles.map((tile) => {
          const Icon = tile.icon;
          return (
            <div className="grid min-h-[72px] grid-cols-[38px_minmax(0,1fr)_16px] items-center gap-3 rounded-[4px] border border-friday-line bg-[#151b22] px-3" key={tile.label}>
              <span className={`grid h-8 w-8 place-items-center rounded-[3px] border ${tile.tone}`}>
                <Icon size={16} />
              </span>
              <div className="min-w-0">
                <strong className="block truncate text-[13px] text-white">{tile.label}</strong>
                <span className="mt-1 block truncate text-[12px] text-[#c2cedd]">{tile.detail}</span>
              </div>
              <ChevronRight className="text-[#c8d3df]" size={16} />
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function MemoryConstitution({ privateMemory }) {
  const sensitiveCount = Number(privateMemory?.sensitive_count || 0);
  const rows = [
    { label: "Approval Gate", value: "Active" },
    { label: "Secret Retention", value: "Blocked" },
    { label: "Sensitive Chunks", value: String(sensitiveCount) }
  ];
  return (
    <Panel className="p-3">
      <div className="flex items-center gap-2">
        <PanelTitle title="Memory Constitution" tone="text-[#ffbf7b]" />
        <ShieldCheck className="ml-auto text-[#ffbf7b]" size={15} />
      </div>
      <blockquote className="mt-3 border-l-2 border-[#ffbf7b] bg-[#111820] px-3 py-3">
        <strong className="block text-[12px] text-white">Retention Protocol</strong>
        <p className="mt-2 text-[12px] italic leading-relaxed text-[#d8e2ee]">
          Private memories require approval; secrets and credentials are blocked from retention.
        </p>
      </blockquote>
      <div className="mt-3 grid gap-2">
        {rows.map((row) => (
          <div className="grid min-h-10 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[3px] border border-friday-line bg-[#303743] px-3" key={row.label}>
            <span className="truncate text-[13px] text-white">{row.label}</span>
            <span className="rounded-[3px] border border-[#5c7088] bg-[#263241] px-2 py-0.5 font-mono text-[10px] uppercase text-friday-accent">{row.value}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ReviewCard({ review, selected, busy, onSelect, onResolve }) {
  const source = sourceMeta(review.source);
  const Icon = source.icon;
  const confidence = confidenceLabel(review);
  const itemBusy = (decision) => busy === `${decision}:${review.id}`;
  return (
    <article className={`min-w-0 rounded-[6px] border bg-[#151b22] p-3 transition-colors ${selected ? "border-friday-accent" : "border-friday-line"}`}>
      <header className="grid min-w-0 grid-cols-[28px_34px_minmax(0,1fr)_auto] items-start gap-3">
        <button
          className={`mt-1 grid h-5 w-5 place-items-center rounded-[3px] border transition-colors ${selected ? "border-friday-accent bg-friday-accent text-[#061420]" : "border-friday-line bg-[#10161d] text-transparent"}`}
          type="button"
          onClick={onSelect}
          aria-label={selected ? "Deselect memory review" : "Select memory review"}
        >
          <CheckCircle2 size={13} />
        </button>
        <span className={`grid h-8 w-8 place-items-center rounded-[3px] border ${source.tone}`}>
          <Icon size={15} />
        </span>
        <div className="min-w-0">
          <strong className="block truncate text-[13px] text-white">{review.title || "Memory review item"}</strong>
          <span className="mt-0.5 block truncate text-[12px] text-[#c4cfdd]">
            {source.label} · {timeAgo(review.created_at)}
          </span>
        </div>
        <span className={`shrink-0 rounded-[3px] border px-2 py-1 font-mono text-[11px] uppercase ${confidence.tone}`}>{confidence.label}</span>
      </header>

      <div className="mt-3 border-l-2 border-[#9fcaff] bg-[#111820] px-4 py-3">
        <p className="m-0 text-[15px] leading-relaxed text-[#e6edf7]">"{trimText(review.content || review.question || "No memory content available.", 320)}"</p>
      </div>

      <footer className="mt-3 grid gap-3 md:grid-cols-[minmax(90px,.45fr)_minmax(0,1fr)] md:items-center">
        <p className="m-0 text-[12px] italic leading-snug text-[#c2cedd]">{review.question || "Is this still true?"}</p>
        <div className="grid min-w-0 grid-cols-3 gap-2">
          <ActionButton
            icon={itemBusy("keep") ? <Loader2 className="animate-spin" size={14} /> : <CheckCircle2 size={14} />}
            label="Keep"
            disabled={Boolean(busy)}
            onClick={() => onResolve(review.id, "keep")}
          />
          <ActionButton
            icon={itemBusy("update") ? <Loader2 className="animate-spin" size={14} /> : <Edit3 size={14} />}
            label="Update"
            disabled={Boolean(busy)}
            onClick={() => onResolve(review.id, "update")}
          />
          <ActionButton
            icon={itemBusy("forget") ? <Loader2 className="animate-spin" size={14} /> : <Trash2 size={14} />}
            label="Forget"
            disabled={Boolean(busy)}
            danger
            onClick={() => onResolve(review.id, "forget")}
          />
        </div>
      </footer>
    </article>
  );
}

function ActionButton({ icon, label, danger, disabled, onClick }) {
  return (
    <button
      className={`inline-flex min-h-9 min-w-0 items-center justify-center gap-2 rounded-[4px] border px-2 text-[12px] font-semibold transition-colors disabled:opacity-50 ${
        danger ? "border-[#4a3f45] bg-[#242126] text-[#f1c2c5] hover:border-[#ff9fa7]" : "border-friday-line bg-[#303743] text-[#edf4ff] hover:border-friday-accent"
      }`}
      type="button"
      onClick={onClick}
      disabled={disabled}
    >
      <span className="shrink-0">{icon}</span>
      <span className="min-w-0 truncate">{label}</span>
    </button>
  );
}

function EmptyQueue({ icon, title, detail, actionLabel, busy, onAction }) {
  return (
    <div className="grid min-h-[300px] place-items-center rounded-[6px] border border-friday-line bg-[#151b22] p-6 text-center">
      <div className="grid max-w-[420px] justify-items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-[6px] border border-[#45678c] bg-[#172334] text-friday-accent">{icon}</span>
        <div>
          <strong className="block text-[16px] text-white">{title}</strong>
          <p className="mt-2 text-[13px] leading-relaxed text-[#c2cedd]">{detail}</p>
        </div>
        {actionLabel ? (
          <button
            className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-[#44607e] bg-[#172334] px-4 font-mono text-[11px] font-bold text-friday-accent transition-colors hover:border-friday-accent disabled:opacity-50"
            type="button"
            onClick={onAction}
            disabled={busy}
          >
            {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Panel({ className = "", children }) {
  return <section className={`min-w-0 rounded-[6px] border border-friday-line bg-[#151b22] ${className}`}>{children}</section>;
}

function PanelTitle({ title, tone = "text-friday-accent" }) {
  return <h3 className={`m-0 font-mono text-[11px] font-bold uppercase tracking-[.16em] ${tone}`}>{title}</h3>;
}

function buildKnowledgeTiles({ projects, knowledgeGraph, privateMemory, reviews, data }) {
  const projectCount = projects.length;
  const graphNodes = Number(knowledgeGraph?.nodes || 0);
  const graphEdges = Number(knowledgeGraph?.edges || 0);
  const privateCount = Number(privateMemory?.count || 0);
  const missionCount = Number(data.missions?.length || 0);
  return [
    { label: "User Preferences", detail: `${privateCount} private memory chunk${privateCount === 1 ? "" : "s"}`, icon: Brain, tone: "border-[#45678c] bg-[#172334] text-friday-accent" },
    { label: "Project Memories", detail: `${projectCount} project${projectCount === 1 ? "" : "s"} indexed`, icon: Folder, tone: "border-[#6b4d78] bg-[#2a1f34] text-[#f0a6ff]" },
    { label: "People & Entities", detail: `${graphNodes} nodes, ${graphEdges} links`, icon: Users, tone: "border-[#755136] bg-[#2b2118] text-[#ffb277]" },
    { label: "Core Goals", detail: `${missionCount} active objective${missionCount === 1 ? "" : "s"}`, icon: Flag, tone: "border-[#45678c] bg-[#172334] text-friday-accent" },
    { label: "Corrections", detail: `${reviews.length} pending review${reviews.length === 1 ? "" : "s"}`, icon: Zap, tone: "border-[#764b4b] bg-[#2c1f22] text-[#ffaaa6]" }
  ];
}

function sourceMeta(source) {
  const normalized = String(source || "").toLowerCase();
  if (normalized.includes("crm")) return { label: "People Memory", icon: User, tone: "border-[#755136] bg-[#2b2118] text-[#ffb277]" };
  if (normalized.includes("project")) return { label: "Project Memory", icon: Folder, tone: "border-[#45678c] bg-[#172334] text-friday-accent" };
  if (normalized.includes("knowledge")) return { label: "Knowledge Vault", icon: Database, tone: "border-[#6b4d78] bg-[#2a1f34] text-[#f0a6ff]" };
  return { label: "Memory Engine", icon: Brain, tone: "border-[#45678c] bg-[#172334] text-friday-accent" };
}

function confidenceLabel(review) {
  const raw = review?.metadata?.confidence;
  if (typeof raw !== "number") return { label: "Confidence: n/a", tone: "border-friday-line bg-[#202733] text-[#cbd7e6]" };
  const percent = Math.round(Math.max(0, Math.min(1, raw)) * 100);
  const tone = percent >= 85 ? "border-[#45678c] bg-[#172334] text-friday-accent" : percent >= 65 ? "border-[#6a4215] bg-[#2a2115] text-[#ffb56d]" : "border-[#59323c] bg-[#28171d] text-[#ff9fa7]";
  return { label: `Confidence: ${percent}%`, tone };
}

function memoryDecisionText(decision) {
  if (decision === "forget") return "Memory marked for forgetting.";
  if (decision === "update") return "Memory marked for update.";
  return "Memory kept successfully.";
}

function timeAgo(value) {
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return "unknown time";
  const seconds = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return new Date(value).toLocaleDateString([], { month: "short", day: "numeric" });
}

function trimText(value, limit) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1)).trim()}...`;
}
