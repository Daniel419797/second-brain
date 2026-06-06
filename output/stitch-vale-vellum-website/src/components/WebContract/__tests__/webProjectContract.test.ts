import { describe, expect, it } from 'vitest';
import { webProject } from '@/lib/webProjectContract';

describe('web project contract', () => {
  it('keeps requested routes explicit', () => {
    expect(webProject.routes.length).toBeGreaterThan(1);
    expect(webProject.routes[0].route).toBe('/');
  });

  it('keeps product-domain terms available for gates', () => {
    expect(webProject.domain_terms.length).toBeGreaterThan(2);
  });
});
