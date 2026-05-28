package com.friday.companion;

import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONObject;

public class FridayNotificationListenerService extends NotificationListenerService {
    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("device_id", Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID));
            payload.put("package", sbn.getPackageName());
            CharSequence title = sbn.getNotification().extras.getCharSequence("android.title");
            CharSequence text = sbn.getNotification().extras.getCharSequence("android.text");
            payload.put("title", title == null ? "" : title.toString());
            payload.put("text", text == null ? "" : text.toString());
            new Thread(() -> {
                try {
                    FridayApi.post(this, "/android-companion/app/notification", payload);
                } catch (Exception ignored) {
                    // The companion should never crash because the laptop API is offline.
                }
            }).start();
        } catch (Exception ignored) {
        }
    }
}
