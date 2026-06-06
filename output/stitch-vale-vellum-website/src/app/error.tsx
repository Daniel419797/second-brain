'use client';

import { Button } from '@/components/ui/button';

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="error-state">
      <h1>Something needs attention</h1>
      <p>The app caught an error before it could finish this view.</p>
      <Button type="button" onClick={reset}>Try again</Button>
    </main>
  );
}
