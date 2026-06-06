export type WorkStatus = 'Captured' | 'AI Brief' | 'Ready' | 'Reviewed';

export type WorkItem = {
  id: string;
  title: string;
  detail: string;
  owner: string;
  status: WorkStatus;
  priority: 'high' | 'medium' | 'low';
};

export type ProductPlan = {
  name: string;
  request: string;
  heroLabel: string;
  summary: string;
  workspaceLabel: string;
  briefTitle: string;
  briefAction: string;
  briefEmpty: string;
  launchTitle: string;
  sampleNote: string;
  workItems: WorkItem[];
  metricCards: Array<{ label: string; value: number }>;
  valueProps: Array<{ title: string; detail: string }>;
  targetUsers: string[];
  integrations: string[];
  pricing: string[];
  launchPlan: string[];
};

export type DecisionBrief = {
  summary: string;
  nextAction: string;
  risks: string;
};

export const productPlan: ProductPlan = {
  name: "Vale & Vellum",
  request: "Build a four-page website for Vale & Vellum, a boutique stationery and wedding invitation studio. Pages must be Home, Collections, Process, Inquiry. Use the selected Google Stitch design direction already saved under .friday/design/pages. Friday should convert the selected Stitch handoff into a real Next.js frontend without manual code edits.",
  heroLabel: "Vale & Vellum command workspace",
  summary: "A focused vale & vellum command workspace for four, page, vale, vellum, and boutique.",
  workspaceLabel: "Vale & Vellum operations",
  briefTitle: "Vale & Vellum Decision Brief",
  briefAction: "Generate operational brief",
  briefEmpty: "Generate a brief from four, page, vale, blockers, and next actions.",
  launchTitle: "Vale & Vellum launch path",
  sampleNote: "Vale & Vellum needs attention on four, page, and vale before the next operational review.",
  workItems: [
  {
    "detail": "Track four with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
    "id": "four-lane",
    "owner": "Operations lead",
    "priority": "high",
    "status": "Captured",
    "title": "Four"
  },
  {
    "detail": "Track page with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
    "id": "page-lane",
    "owner": "AI coordinator",
    "priority": "high",
    "status": "AI Brief",
    "title": "Page"
  },
  {
    "detail": "Track vale with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
    "id": "vale-lane",
    "owner": "Team lead",
    "priority": "medium",
    "status": "Ready",
    "title": "Vale"
  },
  {
    "detail": "Track vellum with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
    "id": "vellum-lane",
    "owner": "Customer desk",
    "priority": "medium",
    "status": "Captured",
    "title": "Vellum"
  },
  {
    "detail": "Track boutique with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
    "id": "boutique-lane",
    "owner": "Finance owner",
    "priority": "medium",
    "status": "Ready",
    "title": "Boutique"
  },
  {
    "detail": "Track stationery with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
    "id": "stationery-lane",
    "owner": "Launch owner",
    "priority": "low",
    "status": "AI Brief",
    "title": "Stationery"
  }
],
  metricCards: [
  {
    "label": "four",
    "value": 12
  },
  {
    "label": "page",
    "value": 5
  },
  {
    "label": "vale",
    "value": 3
  }
],
  valueProps: [
  {
    "detail": "Four, Page, and Vale are tracked by urgency, owner, and next action.",
    "title": "Vale & Vellum pressure becomes visible"
  },
  {
    "detail": "Friday turns four, page, vale, vellum, and boutique into concise briefs with risk, customer impact, and proof for the next operator.",
    "title": "Decisions carry context"
  },
  {
    "detail": "Tests, audits, preview checks, launch approvals, and unresolved gaps stay visible before readiness claims.",
    "title": "Proof stays attached"
  }
],
  targetUsers: [
  "vale & vellum operators",
  "vale & vellum managers",
  "team leads",
  "customer-facing staff",
  "operations owners"
],
  integrations: [
  "csv import/export",
  "google calendar",
  "slack"
],
  pricing: [
  "Vale & Vellum pilot: free for one workspace",
  "$49/month Operator",
  "$149/month Team Operations"
],
  launchPlan: [
  "Validate four workflow",
  "Import sample vale & vellum data",
  "Connect page source",
  "Review privacy, security, and approval controls",
  "Approve vale & vellum launch"
],
};

export function createDecisionBrief(note: string, items: WorkItem[]): DecisionBrief {
  const cleanNote = note.trim() || productPlan.sampleNote;
  const highestPriority = items.find((item) => item.priority === 'high') ?? items[0];
  const blockers = items.filter((item) => item.status !== 'Reviewed').map((item) => item.owner);
  return {
    summary: `Summary: ${cleanNote}`,
    nextAction: `Next action: ${highestPriority?.owner ?? 'Operator'} should move "${highestPriority?.title ?? 'the active workflow'}" forward.`,
    risks: blockers.length ? `Risks: unresolved handoffs for ${Array.from(new Set(blockers)).join(', ')}.` : 'Risks: no open blockers recorded.',
  };
}

export function markWorkItemReviewed(items: WorkItem[], id: string): WorkItem[] {
  return items.map((item) => (item.id === id ? { ...item, status: 'Reviewed' } : item));
}
