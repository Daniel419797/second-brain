import { apiClient } from '@/services/api';
import { createDecisionBrief, productPlan, type DecisionBrief, type WorkItem } from '@/lib/productPlan';

export type DraftBriefRequest = {
  note: string;
  items: WorkItem[];
};

export function normalizeBrief(value: unknown): DecisionBrief {
  const body = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  return {
    summary: typeof body.summary === 'string' ? body.summary : 'Summary: no brief returned.',
    nextAction: typeof body.nextAction === 'string' ? body.nextAction : 'Next action: verify the source workflow.',
    risks: typeof body.risks === 'string' ? body.risks : 'Risks: missing API evidence.',
  };
}

export const BriefService = {
  async fetch() {
    const response = await apiClient.get('/brief');
    return normalizeBrief(response.data);
  },

  async draft(payload: DraftBriefRequest) {
    const response = await apiClient.post('/brief', payload);
    return normalizeBrief(response.data);
  },

  async localDraft(payload: DraftBriefRequest) {
    return createDecisionBrief(payload.note || productPlan.sampleNote, payload.items.length ? payload.items : productPlan.workItems);
  },
};
