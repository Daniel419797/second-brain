import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { webProject } from '@/lib/webProjectContract';

type ContractNavItem = { id: string; label: string; route: string };

export function ContractShell({ children }: { children: React.ReactNode }) {
  const nav = webProject.nav as readonly ContractNavItem[];
  const contactRoute = nav.find((item) => item.id === 'contact')?.route;
  const ctaRoute = contactRoute ?? nav[1]?.route ?? '/';
  const ctaLabel = contactRoute ? 'Book demo' : 'Open workflow';
  return (
    <div className={`contract-site contract-site-${webProject.archetype}`}>
      <header className="contract-nav">
        <Link href="/" className="contract-brand">{webProject.product_name}</Link>
        <nav aria-label="Primary navigation">
          {nav.map((item) => (
            <Link key={item.id} href={item.route}>{item.label}</Link>
          ))}
        </nav>
        <Link href={ctaRoute} className="contract-nav-cta">
          {ctaLabel} <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </header>
      {children}
      <footer className="contract-footer">
        <strong>{webProject.product_name}</strong>
        <span>{webProject.tone}</span>
      </footer>
    </div>
  );
}
