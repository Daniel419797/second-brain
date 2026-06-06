export const webProject = {
  "acceptance": [
    "Every requested page/route has a real Next.js App Router file.",
    "Route files stay thin and compose feature/page components.",
    "Visible copy uses product-domain terms, not scaffold filler.",
    "Primary links route to existing pages or change visible state.",
    "Browser smoke checks all contract routes."
  ],
  "archetype": "product_studio",
  "dashboard_preview": {},
  "domain_terms": [
    "four",
    "vale",
    "vellum",
    "boutique",
    "stationery",
    "wedding",
    "invitation",
    "must",
    "collections",
    "process"
  ],
  "nav": [
    {
      "id": "home",
      "kind": "public",
      "label": "Home",
      "route": "/"
    },
    {
      "id": "collections",
      "kind": "public",
      "label": "Collections",
      "route": "/collections"
    },
    {
      "id": "process",
      "kind": "public",
      "label": "Process",
      "route": "/process"
    },
    {
      "id": "contact",
      "kind": "public",
      "label": "Contact",
      "route": "/contact"
    }
  ],
  "pages": [
    {
      "id": "home",
      "label": "Home",
      "primary_action": "Open dashboard preview",
      "route": "/",
      "secondary_action": "View audit trail",
      "sections": [
        {
          "body": "Four gets an owner, status, blocker, public/customer impact, and proof trail.",
          "title": "Four without spreadsheet drift"
        },
        {
          "body": "Vale gets an owner, status, blocker, public/customer impact, and proof trail.",
          "title": "Vale without spreadsheet drift"
        },
        {
          "body": "Vellum gets an owner, status, blocker, public/customer impact, and proof trail.",
          "title": "Vellum without spreadsheet drift"
        },
        {
          "body": "Boutique gets an owner, status, blocker, public/customer impact, and proof trail.",
          "title": "Boutique without spreadsheet drift"
        }
      ],
      "summary": "Designed around four, vale, vellum, boutique, stationery with visible owners, status, blockers, updates, and proof.",
      "title": "Vale & Vellum turns four, vale, vellum into accountable work."
    },
    {
      "id": "collections",
      "label": "Collections",
      "primary_action": "Book walkthrough",
      "route": "/collections",
      "secondary_action": "View audit trail",
      "sections": [
        {
          "body": "Separate new, aging, blocked, and ownerless collections work before it drifts into another inbox.",
          "title": "Collections queue pressure"
        },
        {
          "body": "Show the reviewer, counter staff, inspector, or approver responsible for the next collections decision.",
          "title": "Owner and handoff clarity"
        },
        {
          "body": "Surface due dates, fee holds, missing documents, capacity conflicts, and public-update risk for collections.",
          "title": "Risk and SLA controls"
        },
        {
          "body": "Attach notes, status changes, applicant messages, and decision history so collections claims can be verified.",
          "title": "Audit proof"
        }
      ],
      "summary": "Track collections, owners, blockers, handoffs, aging, public updates, and audit proof for Vale & Vellum.",
      "title": "Collections command view for collections."
    },
    {
      "id": "process",
      "label": "Process",
      "primary_action": "Book walkthrough",
      "route": "/process",
      "secondary_action": "View audit trail",
      "sections": [
        {
          "body": "Separate new, aging, blocked, and ownerless process work before it drifts into another inbox.",
          "title": "Process queue pressure"
        },
        {
          "body": "Show the reviewer, counter staff, inspector, or approver responsible for the next process decision.",
          "title": "Owner and handoff clarity"
        },
        {
          "body": "Surface due dates, fee holds, missing documents, capacity conflicts, and public-update risk for process.",
          "title": "Risk and SLA controls"
        },
        {
          "body": "Attach notes, status changes, applicant messages, and decision history so process claims can be verified.",
          "title": "Audit proof"
        }
      ],
      "summary": "Track process, owners, blockers, handoffs, aging, public updates, and audit proof for Vale & Vellum.",
      "title": "Process command view for process."
    },
    {
      "id": "contact",
      "label": "Contact",
      "primary_action": "Book walkthrough",
      "route": "/contact",
      "secondary_action": "View audit trail",
      "sections": [
        {
          "body": "Tell us where four stalls and who owns the next decision.",
          "title": "Workflow pressure"
        },
        {
          "body": "Share the systems, spreadsheets, calendars, or inboxes that need to connect.",
          "title": "Data sources"
        },
        {
          "body": "Leave with a specific pilot plan, security notes, and acceptance criteria.",
          "title": "Pilot proof"
        }
      ],
      "summary": "Capture the team, workflow pressure, timeline, and data constraints needed for a real pilot conversation.",
      "title": "Book a focused product walkthrough."
    }
  ],
  "product_name": "Vale & Vellum",
  "request_summary": "Designed around four, vale, vellum, boutique, stationery with visible owners, status, blockers, updates, and proof.",
  "routes": [
    {
      "id": "home",
      "kind": "public",
      "label": "Home",
      "route": "/"
    },
    {
      "id": "collections",
      "kind": "public",
      "label": "Collections",
      "route": "/collections"
    },
    {
      "id": "process",
      "kind": "public",
      "label": "Process",
      "route": "/process"
    },
    {
      "id": "contact",
      "kind": "public",
      "label": "Contact",
      "route": "/contact"
    }
  ],
  "tone": "specific, polished, useful, evidence-led",
  "version": "friday_web_contract_v1"
} as const;

export type WebProject = typeof webProject;
