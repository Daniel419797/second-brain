import { AlertTriangle, CalendarDays, CheckCircle2, UsersRound } from 'lucide-react';
import { ContractShell } from '@/components/WebContract/ContractShell';
import { webProject } from '@/lib/webProjectContract';

type DashboardMetric = { label: string; value: string; tone: string };
type DashboardQueueItem = { title: string; owner: string; status: string };
type DashboardPreview = {
  title?: string;
  summary?: string;
  metrics?: DashboardMetric[];
  queue?: DashboardQueueItem[];
};

export function DashboardPreviewPage() {
  const dashboard = webProject.dashboard_preview as DashboardPreview;
  const metrics = Array.isArray(dashboard.metrics) ? dashboard.metrics : [];
  const queue = Array.isArray(dashboard.queue) ? dashboard.queue : [];
  return (
    <ContractShell>
      <main className="contract-dashboard">
        <section className="contract-dashboard-head">
          <p className="contract-eyebrow">operations dashboard preview</p>
          <h1>{dashboard.title ?? `${webProject.product_name} dashboard`}</h1>
          <p>{dashboard.summary ?? webProject.request_summary}</p>
        </section>
        <section className="contract-metrics" aria-label="Operational metrics">
          {metrics.map((metric) => (
            <article key={metric.label} className={`contract-metric ${metric.tone}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </article>
          ))}
        </section>
        <section className="contract-dashboard-grid">
          <article className="contract-board">
            <div className="contract-board-title"><AlertTriangle size={20} />Urgent queue</div>
            {queue.map((item) => (
              <div key={item.title} className="contract-queue-row">
                <strong>{item.title}</strong>
                <span>{item.owner}</span>
                <em>{item.status}</em>
              </div>
            ))}
          </article>
          <article className="contract-board">
            <div className="contract-board-title"><CalendarDays size={20} />Schedule load</div>
            <div className="contract-calendar">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].map((day, index) => (
                <span key={day} style={{ '--load': `${50 + index * 9}%` } as React.CSSProperties}>{day}</span>
              ))}
            </div>
          </article>
          <article className="contract-board">
            <div className="contract-board-title"><UsersRound size={20} />Reviewer workload</div>
            {webProject.domain_terms.slice(0, 4).map((term) => (
              <div key={term} className="contract-workload"><span>{term}</span><CheckCircle2 size={16} /></div>
            ))}
          </article>
        </section>
      </main>
    </ContractShell>
  );
}
