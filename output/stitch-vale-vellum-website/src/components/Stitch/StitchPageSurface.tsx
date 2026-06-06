import { StitchNativePage } from './StitchNativePage';
import type { StitchPageId } from '@/lib/stitchNativeContent';

export function StitchPageSurface({ page }: { page: StitchPageId }) {
  return <StitchNativePage page={page} />;
}
