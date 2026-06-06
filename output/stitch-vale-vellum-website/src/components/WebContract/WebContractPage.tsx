import Link from 'next/link';
import { ArrowRight, CheckCircle2, ClipboardList, FileCheck2, MapPinned } from 'lucide-react';
import { ContractShell } from '@/components/WebContract/ContractShell';
import { webProject } from '@/lib/webProjectContract';

type ContractNavItem = { id: string; label: string; route: string };

export function WebContractPage({ pageId }: { pageId: string }) {
  const page = webProject.pages.find((item) => item.id === pageId) ?? webProject.pages[0];
  const dashboard = webProject.dashboard_preview;
  const nav = webProject.nav as readonly ContractNavItem[];
  const currentPageId = String(page.id);
  const showDashboardAction = Boolean(dashboard && 'route' in dashboard);
  const navIndex = Math.max(0, nav.findIndex((item) => item.id === currentPageId));
  const nextRoute = nav[(navIndex + 1) % nav.length]?.route ?? '/';
  const previousRoute = nav[Math.max(0, navIndex - 1)]?.route ?? '/';
  const pricingRoute = nav.find((item) => item.id === 'pricing')?.route;
  const productRoute = nav.find((item) => item.id === 'product')?.route;
  const primaryHref = showDashboardAction ? '/dashboard-preview' : nextRoute;
  const secondaryHref = currentPageId === 'pricing' ? (productRoute ?? previousRoute) : (pricingRoute ?? previousRoute);
  return (
    <ContractShell>
      <section className="contract-hero">
        <div className="contract-hero-grid" aria-hidden="true">
          {webProject.domain_terms.slice(0, 6).map((term, index) => (
            <span key={term} style={{ '--i': index } as React.CSSProperties}>{term}</span>
          ))}
        </div>
        <div className="contract-hero-copy">
          <p className="contract-eyebrow">{webProject.archetype.replace(/_/g, ' ')}</p>
          <h1>{page.title}</h1>
          <p>{page.summary}</p>
          <div className="contract-actions">
            <Link href={primaryHref} className="contract-button primary">
              {page.primary_action} <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <Link href={secondaryHref} className="contract-button secondary">
              {page.secondary_action}
            </Link>
          </div>
        </div>
      </section>

      <section className="contract-proof-strip" aria-label="Contract proof">
        {webProject.acceptance.slice(0, 4).map((item) => (
          <div key={item}><CheckCircle2 size={18} aria-hidden="true" />{item}</div>
        ))}
      </section>

      <section className="contract-section-grid">
        {page.sections.map((section, index) => {
          const Icon = [ClipboardList, MapPinned, FileCheck2][index % 3];
          return (
            <article key={section.title} className="contract-panel">
              <Icon size={22} aria-hidden="true" />
              <h2>{section.title}</h2>
              <p>{section.body}</p>
            </article>
          );
        })}
      </section>

      {currentPageId === 'contact' ? <ContactCapture /> : null}
    </ContractShell>
  );
}

function ContactCapture() {
  return (
    <section className="contract-contact" aria-label="Demo request">
      <div>
        <p className="contract-eyebrow">pilot intake</p>
        <h2>Turn the first call into a scoped pilot.</h2>
        <p>Friday should collect the workflow pressure, systems involved, approval needs, and proof required before anyone claims launch readiness.</p>
      </div>
      <form>
        <label>Team name<input name="team" /></label>
        <label>Workflows to fix<textarea name="workflows" /></label>
        <button type="button">Save demo request</button>
      </form>
    </section>
  );
}
