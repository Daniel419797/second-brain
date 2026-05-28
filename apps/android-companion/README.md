# Friday Android Companion

Native Android companion scaffold for Friday.

Capabilities:

- talk to Friday from the phone using Android speech recognition
- register the phone with the local Friday API
- sync clipboard text
- send battery/status and optional location
- sync notifications through Android Notification Listener permission
- keep camera/file-transfer hooks available through the companion API without sending private media by default

Setup:

1. Start Friday API on your laptop: `python jarvis.py --api`.
2. Find your laptop LAN IP, then use `http://YOUR-LAPTOP-IP:8000` as the API base in the app.
3. Log into the dashboard, copy the Bearer token from local storage or API login response, and paste it into the app.
4. Tap **Save Settings + Register Phone**.
5. Optional: open notification access settings and allow Friday Companion.

Safety:

- The app sends only to your configured local Friday API.
- Notification text and clipboard text are redacted on the server if they look secret-like.
- Camera frame payloads are metadata-only by default; raw image data is replaced with a redaction marker.
