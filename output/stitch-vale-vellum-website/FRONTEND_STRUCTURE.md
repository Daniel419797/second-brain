# Frontend Folder Structure

This scaffold follows the NexusForge-style Next.js frontend layout.

## Project Identity

- Framework: Next.js App Router
- Language: TypeScript, strict mode
- Main source root: `src`
- Import alias: `@/*` -> `src/*`
- Styling/UI: Tailwind-ready CSS, shadcn-style primitives, lucide-react
- Data/API layer: services in `src/services`
- Client state: Zustand stores in `src/store`
- Tests: Vitest, Testing Library, colocated `__tests__`, and `src/test`

## Structure

```txt
src/
|-- app/                         Route groups, layouts, route handlers
|   |-- (auth)/
|   |-- (dashboard)/
|   `-- api/
|-- components/                  Feature UI and reusable primitives
|   |-- Auth/
|   |-- Landing/
|   |-- Workspace/
|   |-- Shared/
|   |-- layout/
|   `-- ui/
|-- hooks/                       Cross-feature React hooks
|-- lib/                         Shared utilities, security, domain helpers
|-- services/                    Backend API clients and service tests
|-- store/                       Client stores
|-- test/                        Test setup and render helpers
`-- types/                       Shared TypeScript contracts
```

## Replication Rules

1. Keep route files thin.
2. Put real feature UI in `src/components/<FeatureName>`.
3. Put generic primitives in `src/components/ui`.
4. Put API clients in `src/services`.
5. Put shared client state in `src/store`.
6. Put reusable hooks in `src/hooks`.
7. Put shared utilities and framework helpers in `src/lib`.
8. Put shared DTOs and contracts in `src/types`.
9. Keep tests close to the code they validate.
10. Use `@/` imports for anything inside `src`.

## Web Route Contract

- `src/lib/webProjectContract.ts` stores requested pages, nav, dashboard preview content, domain terms, and acceptance criteria.
- `src/components/WebContract` renders contract pages from data instead of scattering page copy through route files.
- Requested pages/routes must exist before product gates can pass.
