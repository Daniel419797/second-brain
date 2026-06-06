import { describe, expect, it } from 'vitest';
import { markWorkItemReviewed, productPlan } from '@/lib/productPlan';

describe('workspace state helpers', () => {
  it('marks a work item reviewed without mutating the original list', () => {
    const updated = markWorkItemReviewed(productPlan.workItems, productPlan.workItems[0].id);
    expect(updated[0].status).toBe('Reviewed');
    expect(productPlan.workItems[0].status).not.toBe('Reviewed');
  });
});
