import { describe, expect, it } from 'vitest';
import { normalizeBrief } from '@/services/BriefService';

describe('normalizeBrief', () => {
  it('keeps structured brief fields', () => {
    expect(normalizeBrief({ summary: 'Summary: ok', nextAction: 'Next action: ship', risks: 'Risks: none' })).toEqual({
      summary: 'Summary: ok',
      nextAction: 'Next action: ship',
      risks: 'Risks: none',
    });
  });
});
