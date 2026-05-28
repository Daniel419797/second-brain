# Google Workspace OAuth Setup

Friday can use real Google OAuth for Gmail, Calendar, Docs, and Sheets. This is different from opening the web UI: Friday receives a Google access token after you consent, then uses official Google APIs.

## Required Google Cloud Setup

1. Create or open a Google Cloud project.
2. Configure the OAuth consent screen.
3. Create an OAuth Client ID for a web application.
4. Add this authorized redirect URI:

```text
http://127.0.0.1:8000/oauth/google/callback
```

5. Add these values to `.env`:

```text
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
```

6. Restart the API:

```powershell
.\.venv\Scripts\python.exe jarvis.py --api
```

7. Open the dashboard, go to Integrations, and click **Connect Google**.

## Scopes Friday Requests

- Gmail read-only access
- Calendar event read/write
- Google Docs create/write
- Google Sheets create/write
- Basic Google email identity

The token is stored locally at `data/google_oauth_token.json`, which is ignored by git.

## Safety Notes

Friday does not bypass login, CAPTCHA, or consent. If OAuth is not configured or connected, it reports that clearly and falls back to local data or web-app opening.
