'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

import { stitchNativeContent, type StitchPageId } from '@/lib/stitchNativeContent';

import styles from './StitchNativePage.module.css';

type NativeAction = { label: string; href: string; primary: boolean };
type NativeVisual = { src: string; alt: string };
type NativeCard = { title: string; body: string };
type NativeSection = { label: string; title: string; body: string; cards: readonly NativeCard[]; points: readonly string[] };
type NativeProof = { kicker: string; title: string; body: string; items: readonly string[] };
type NativePage = {
  actions: readonly NativeAction[];
  bodyHtml?: string;
  documentHtml?: string;
  kind: string;
  kicker: string;
  label: string;
  renderMode?: string;
  route: string;
  score: number;
  sections: readonly NativeSection[];
  summary: string;
  styleHtml?: string;
  tailwindConfig?: string;
  title: string;
  usesTailwindCdn?: boolean;
  visuals: readonly NativeVisual[];
  proof: NativeProof;
};

export function StitchNativePage({ page }: { page: StitchPageId }) {
  const pages = stitchNativeContent.pages as Record<StitchPageId, NativePage>;
  const data = pages[page];
  const meta = stitchNativeContent.meta;
  const nav = meta.nav.length ? meta.nav : Object.values(pages).map((item) => ({ label: item.label, href: item.route }));
  const heroVisual = data.visuals[0];
  const headerAction = meta.primaryAction || data.actions.find((action) => action.primary) || data.actions[0] || { label: 'Get started', href: data.route || '/', primary: true };
  const proof = data.proof || { kicker: 'Proof', title: meta.productName, body: data.summary, items: [] };
  const renderStitchDocument = data.renderMode === 'stitch_document' && Boolean(data.documentHtml);
  const renderStitchHtml = data.renderMode === 'stitch_html' && Boolean(data.bodyHtml);

  if (renderStitchDocument) {
    return (
      <main className={`${styles.shell} ${styles.documentShell}`} aria-label={`${data.title} page`}>
        <StitchDocumentRuntime pageId={String(page)} data={data} />
      </main>
    );
  }

  if (renderStitchHtml) {
    return (
      <main className={`${styles.shell} ${styles.fidelityShell}`} aria-label={`${data.title} page`}>
        <StitchHtmlRuntime pageId={String(page)} data={data} />
      </main>
    );
  }

  return (
    <main className={styles.shell} aria-label={`${data.title} page`}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand}>{meta.productName}</Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          {nav.map((item) => (
            <Link key={`${item.href}-${item.label}`} href={item.href} className={item.href === data.route ? styles.activeNav : styles.navLink}>
              {item.label}
            </Link>
          ))}
        </nav>
        <Link href={headerAction.href} className={styles.headerAction}>{headerAction.label}</Link>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          {data.kicker ? <p className={styles.eyebrow}>{data.kicker}</p> : null}
          <h1>{data.title}</h1>
          <p className={styles.summary}>{data.summary}</p>
          <div className={styles.actions}>
            {data.actions.length ? data.actions.slice(0, 2).map((action) => (
              <Link key={`${action.href}-${action.label}`} href={action.href} className={action.primary ? styles.primaryAction : styles.secondaryAction}>
                {action.label}
              </Link>
            )) : <Link href={headerAction.href} className={styles.primaryAction}>{headerAction.label}</Link>}
          </div>
        </div>
        {heroVisual ? (
          <div className={styles.visualPanel}>
            <img src={heroVisual.src} alt={heroVisual.alt || data.title} />
          </div>
        ) : (
          <div className={styles.signalPanel}>
            <p className={styles.eyebrow}>{proof.kicker}</p>
            <h2>{proof.title}</h2>
            <p>{proof.body}</p>
            {proof.items.length ? (
              <ul className={styles.signalList}>
                {proof.items.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
          </div>
        )}
      </section>

      {data.sections.map((section, index) => (
        <section key={`${section.title}-${index}`} className={styles.section}>
          <div className={styles.sectionHeader}>
            <p className={styles.eyebrow}>{section.label || `Section ${index + 1}`}</p>
            <h2>{section.title}</h2>
            {section.body ? <p>{section.body}</p> : null}
          </div>
          {section.cards.length ? (
            <div className={styles.cardGrid}>
              {section.cards.map((card) => (
                <article key={`${card.title}-${card.body}`} className={styles.card}>
                  <h3>{card.title}</h3>
                  <p>{card.body}</p>
                </article>
              ))}
            </div>
          ) : null}
          {section.points.length ? (
            <ul className={styles.pointList}>
              {section.points.map((point) => <li key={point}>{point}</li>)}
            </ul>
          ) : null}
        </section>
      ))}

      {data.kind === 'contact' ? <ContactBlock productName={meta.productName} /> : null}
    </main>
  );
}

function StitchDocumentRuntime({ pageId, data }: { pageId: string; data: NativePage }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState('100vh');

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const updateHeight = () => {
      if (cancelled) {
        return;
      }
      attempts += 1;
      const doc = iframeRef.current?.contentDocument;
      const nextHeight = Math.max(
        doc?.documentElement?.scrollHeight || 0,
        doc?.body?.scrollHeight || 0,
        window.innerHeight || 0,
      );
      if (nextHeight > 0) {
        setHeight(`${nextHeight}px`);
      }
      if (attempts < 8) {
        window.setTimeout(updateHeight, 600);
      }
    };
    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => {
      cancelled = true;
      window.removeEventListener('resize', updateHeight);
    };
  }, [pageId, data.documentHtml]);

  return (
    <iframe
      ref={iframeRef}
      title={`${data.title} Stitch design`}
      className={styles.stitchDocumentFrame}
      srcDoc={data.documentHtml || ''}
      sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
      style={{ height }}
    />
  );
}

function StitchHtmlRuntime({ pageId, data }: { pageId: string; data: NativePage }) {
  useEffect(() => {
    if (!data.usesTailwindCdn || typeof document === 'undefined') {
      return;
    }
    const runtimeId = `stitch-runtime-${pageId}`;
    const existing = document.querySelector(`script[data-friday-stitch-tailwind="${runtimeId}"]`);
    if (existing) {
      return;
    }
    const configScript = document.createElement('script');
    configScript.dataset.fridayStitchTailwind = `${runtimeId}-config`;
    configScript.text = data.tailwindConfig || 'window.tailwind = window.tailwind || {};';
    document.head.appendChild(configScript);

    const cdnScript = document.createElement('script');
    cdnScript.dataset.fridayStitchTailwind = runtimeId;
    cdnScript.src = 'https://cdn.tailwindcss.com?plugins=forms,container-queries';
    cdnScript.async = false;
    document.head.appendChild(cdnScript);

    return () => {
      configScript.remove();
      cdnScript.remove();
    };
  }, [data.tailwindConfig, data.usesTailwindCdn, pageId]);

  return (
    <>
      {data.styleHtml ? <style dangerouslySetInnerHTML={{ __html: data.styleHtml }} /> : null}
      <div className={styles.stitchHtmlSurface} dangerouslySetInnerHTML={{ __html: data.bodyHtml || '' }} />
    </>
  );
}

function ContactBlock({ productName }: { productName: string }) {
  const [submitted, setSubmitted] = useState(false);

  return (
    <section className={styles.contactBlock}>
      <div>
        <p className={styles.eyebrow}>Project inquiry</p>
        <h2>Start a conversation with {productName}</h2>
        <p>Share the project type, location, timing, and the team that should respond. This form is ready to connect to the approved CRM or email workflow.</p>
      </div>
      <form className={styles.form} onSubmit={(event) => { event.preventDefault(); setSubmitted(true); }}>
        <label>Name<input name="name" type="text" placeholder="Jane Doe" /></label>
        <label>Email<input name="email" type="email" placeholder="jane@company.com" /></label>
        <label>Project<textarea name="project" placeholder="Project type, location, timing, and contact path" /></label>
        <button type="submit">Submit inquiry</button>
        {submitted ? <p className={styles.formStatus} role="status">Inquiry draft captured for this preview. Connect the approved inbox or CRM before launch.</p> : null}
      </form>
    </section>
  );
}
