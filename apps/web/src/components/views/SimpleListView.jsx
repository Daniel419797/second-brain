import { STATUSES } from "@/lib/config";
import { Progress } from "@/components/ui/Metric";

export function TasksView({ tasks }) {
  return (
    <section className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <div className="mb-5 flex justify-between gap-3 border-b border-friday-line pb-3">
        <h2 className="m-0 text-2xl font-extrabold">Tasks</h2>
        <span className="text-xs text-friday-muted">{tasks?.length || 0} total tasks</span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {STATUSES.map((status) => (
          <div className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-3" key={status}>
            <div className="mb-3 grid grid-cols-[minmax(0,1fr)_auto] gap-2"><strong>{status}</strong><span className="text-xs text-friday-muted">{tasks.filter((task) => task.status === status).length}</span></div>
            {tasks.filter((task) => task.status === status).slice(0, 8).map((task) => (
              <article className="mb-2 grid gap-2 rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-3" key={task.id}>
                <strong className="block truncate">#{task.id} {task.title}</strong>
                <Progress value={task.progress_percent || 0} />
                <div className="flex flex-wrap gap-1.5">
                  <span className="border border-[#3a4654] bg-[#121922] px-2 py-1 font-mono text-xs">{task.agent_id || "auto"}</span>
                  <span className="border border-[#3a4654] bg-[#121922] px-2 py-1 font-mono text-xs">P{task.priority || 5}</span>
                </div>
              </article>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

export function ApprovalsView({ approvals, summary }) {
  const rows = approvals?.length ? approvals : summary?.items || [];
  return (
    <SimpleView title="Approval Inbox" empty="Friday has no decision gate waiting.">
      {rows.map((item) => (
        <ListRow key={`${item.kind}-${item.id}`} title={item.title} sub={item.summary || item.action_hint || item.kind} />
      ))}
    </SimpleView>
  );
}

export function GenericView({ title, rows = [], empty = "Friday has no row for this surface yet." }) {
  return (
    <SimpleView title={title} empty={empty}>
      {rows.map((item, index) => (
        <ListRow key={item.id || index} title={item.title || item.action || item.name || title} sub={item.summary || item.detail || item.category || item.status} />
      ))}
    </SimpleView>
  );
}

function SimpleView({ title, empty, children }) {
  return (
    <section className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <h2 className="mb-4 text-2xl font-extrabold">{title}</h2>
      <div className="grid gap-3">
        {children?.length ? children : <div className="grid min-h-20 place-items-center text-center text-friday-muted">{empty}</div>}
      </div>
    </section>
  );
}

function ListRow({ title, sub }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-b border-friday-line py-2">
      <div>
        <strong className="block truncate">{title}</strong>
        <span className="text-xs text-friday-muted">{sub || "Friday has no extra detail attached yet."}</span>
      </div>
    </div>
  );
}
