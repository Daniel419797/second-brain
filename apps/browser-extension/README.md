# Friday Local Context Bridge

Manifest V3 extension for Chrome and Edge. It sends redacted page context and console errors to the local Friday API:

- `POST /browser-extension/context`
- `POST /browser-extension/console`

It does not send password fields, hidden fields, token-like values, query strings, cookies, or private form values.

Load it with Chrome/Edge developer mode from `apps/browser-extension`, then paste a dashboard bearer token into the popup.
