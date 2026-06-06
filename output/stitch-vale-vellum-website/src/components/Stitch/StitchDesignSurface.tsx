import { stitchNativeContent, type StitchPageId } from '@/lib/stitchNativeContent';

import { StitchPageSurface } from './StitchPageSurface';

function defaultPage(): StitchPageId {
  const pages = stitchNativeContent.pages as Record<string, unknown>;
  if ('home' in pages) {
    return 'home' as StitchPageId;
  }
  if ('website_home' in pages) {
    return 'website_home' as StitchPageId;
  }
  return (Object.keys(pages)[0] || 'home') as StitchPageId;
}

export function StitchDesignSurface() {
  return <StitchPageSurface page={defaultPage()} />;
}
