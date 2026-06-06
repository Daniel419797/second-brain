'use client';

import { useState } from 'react';
import { BriefService } from '@/services/BriefService';
import type { DecisionBrief, WorkItem } from '@/lib/productPlan';

export function useBriefDraft() {
  const [brief, setBrief] = useState<DecisionBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function draftBrief(note: string, items: WorkItem[]) {
    setLoading(true);
    setError('');
    try {
      setBrief(await BriefService.draft({ note, items }));
    } catch {
      setError('Local fallback used because the brief API did not respond.');
      setBrief(await BriefService.localDraft({ note, items }));
    } finally {
      setLoading(false);
    }
  }

  return { brief, draftBrief, error, loading };
}
