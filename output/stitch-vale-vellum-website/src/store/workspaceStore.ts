import { create } from 'zustand';
import { markWorkItemReviewed, productPlan, type WorkItem } from '@/lib/productPlan';

type WorkspaceState = {
  items: WorkItem[];
  reviewItem: (id: string) => void;
  reset: () => void;
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  items: productPlan.workItems,
  reviewItem: (id) => set((state) => ({ items: markWorkItemReviewed(state.items, id) })),
  reset: () => set({ items: productPlan.workItems }),
}));
