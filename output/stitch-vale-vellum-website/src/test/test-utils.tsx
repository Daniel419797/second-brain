import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement } from 'react';

export function renderWithApp(ui: ReactElement, options?: RenderOptions) {
  return render(ui, options);
}
