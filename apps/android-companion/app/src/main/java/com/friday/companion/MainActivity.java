package com.friday.companion;

import android.Manifest;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.location.Location;
import android.location.LocationManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.Settings;
import android.speech.RecognizerIntent;
import android.util.Base64;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final int REQ_SPEECH = 101;
    private static final int REQ_FILE = 102;
    private static final int REQ_CAMERA = 103;
    private TextView logView;
    private EditText apiBase;
    private EditText token;
    private EditText commandText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestPermissions(new String[] {
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CAMERA,
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.POST_NOTIFICATIONS,
            Manifest.permission.READ_MEDIA_IMAGES
        }, 5);
        buildUi();
    }

    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = 24;
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("Friday Android Companion");
        title.setTextSize(22);
        root.addView(title);

        apiBase = new EditText(this);
        apiBase.setHint("Friday API base URL, e.g. http://192.168.1.10:8000");
        apiBase.setText(FridayApi.baseUrl(this));
        root.addView(apiBase);

        token = new EditText(this);
        token.setHint("Bearer token from Friday dashboard login");
        token.setText(FridayApi.token(this));
        root.addView(token);

        commandText = new EditText(this);
        commandText.setHint("Type or dictate a Friday command");
        root.addView(commandText);

        addButton(root, "Save Settings + Register Phone", this::saveAndRegister);
        addButton(root, "Speak to Friday", this::startSpeech);
        addButton(root, "Send Typed Command", () -> sendVoice(commandText.getText().toString()));
        addButton(root, "Handoff To PC", () -> handoffToPc(commandText.getText().toString()));
        addButton(root, "Sync Clipboard", this::syncClipboard);
        addButton(root, "Pick File/Photo For Friday", this::pickFile);
        addButton(root, "Capture Camera Snapshot Metadata", this::captureCameraMetadata);
        addButton(root, "Send Status", this::sendStatus);
        addButton(root, "Send Location If Allowed", this::sendLocation);
        addButton(root, "Open Notification Access Settings", () -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));

        logView = new TextView(this);
        logView.setText("Ready.\n");
        root.addView(logView);
        setContentView(scroll);
    }

    private void addButton(LinearLayout root, String label, Runnable runnable) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener((View view) -> runnable.run());
        root.addView(button);
    }

    private void saveAndRegister() {
        FridayApi.prefs(this).edit()
            .putString("api_base", apiBase.getText().toString().trim())
            .putString("token", token.getText().toString().trim())
            .apply();
        try {
            JSONObject payload = baseDevicePayload();
            JSONArray capabilities = new JSONArray();
            capabilities.put("microphone");
            capabilities.put("notifications");
            capabilities.put("clipboard");
            capabilities.put("status");
            capabilities.put("location_if_allowed");
            payload.put("capabilities", capabilities);
            post("/android-companion/app/register", payload);
        } catch (Exception error) {
            log("Register failed: " + error.getMessage());
        }
    }

    private void startSpeech() {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault());
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Talk to Friday");
        startActivityForResult(intent, REQ_SPEECH);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_SPEECH && resultCode == RESULT_OK && data != null) {
            ArrayList<String> matches = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (matches != null && !matches.isEmpty()) {
                commandText.setText(matches.get(0));
                sendVoice(matches.get(0));
            }
        } else if (requestCode == REQ_FILE && resultCode == RESULT_OK && data != null) {
            sendFileMetadata(data.getData());
        } else if (requestCode == REQ_CAMERA && resultCode == RESULT_OK) {
            sendCameraMetadata(data);
        }
    }

    private void sendVoice(String text) {
        try {
            JSONObject payload = new JSONObject();
            payload.put("text", text);
            post("/android-companion/voice", payload);
        } catch (Exception error) {
            log("Voice command failed: " + error.getMessage());
        }
    }

    private void handoffToPc(String text) {
        try {
            JSONObject device = baseDevicePayload();
            JSONObject payload = new JSONObject();
            JSONObject body = new JSONObject();
            body.put("command", text);
            payload.put("device_id", device.optString("device_id", ""));
            payload.put("title", text == null || text.trim().isEmpty() ? "Continue this on PC" : text.trim());
            payload.put("kind", "command");
            payload.put("direction", "phone_to_pc");
            payload.put("payload", body);
            post("/phone-mesh/handoff", payload);
        } catch (Exception error) {
            log("Handoff failed: " + error.getMessage());
        }
    }

    private void syncClipboard() {
        try {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            ClipData clip = clipboard == null ? null : clipboard.getPrimaryClip();
            CharSequence value = clip != null && clip.getItemCount() > 0 ? clip.getItemAt(0).coerceToText(this) : "";
            JSONObject payload = baseDevicePayload();
            payload.put("text", String.valueOf(value));
            post("/android-companion/app/clipboard", payload);
        } catch (Exception error) {
            log("Clipboard sync failed: " + error.getMessage());
        }
    }

    private void pickFile() {
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.setType("*/*");
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(Intent.createChooser(intent, "Send file metadata to Friday"), REQ_FILE);
    }

    private void captureCameraMetadata() {
        Intent intent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        startActivityForResult(intent, REQ_CAMERA);
    }

    private void sendFileMetadata(Uri uri) {
        try {
            JSONObject payload = baseDevicePayload();
            if (uri != null) {
                payload.put("uri", uri.toString());
                payload.put("name", uri.getLastPathSegment());
                payload.put("mime_type", getContentResolver().getType(uri));
                String encoded = readSmallContentBase64(uri, 1_000_000);
                if (!encoded.isEmpty()) {
                    payload.put("content_base64", encoded);
                }
            }
            payload.put("source", "android_picker");
            post("/android-companion/app/file", payload);
        } catch (Exception error) {
            log("File metadata failed: " + error.getMessage());
        }
    }

    private void sendCameraMetadata(Intent data) {
        try {
            JSONObject payload = baseDevicePayload();
            payload.put("source", "android_camera_intent");
            payload.put("thumbnail_present", data != null && data.getExtras() != null && data.getExtras().get("data") != null);
            if (data != null && data.getExtras() != null && data.getExtras().get("data") instanceof Bitmap) {
                Bitmap bitmap = (Bitmap) data.getExtras().get("data");
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                bitmap.compress(Bitmap.CompressFormat.JPEG, 75, out);
                payload.put("name", "camera_snapshot.jpg");
                payload.put("mime_type", "image/jpeg");
                payload.put("image_base64", Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP));
            }
            payload.put("captured_at", System.currentTimeMillis());
            post("/android-companion/app/camera-frame", payload);
        } catch (Exception error) {
            log("Camera metadata failed: " + error.getMessage());
        }
    }

    private String readSmallContentBase64(Uri uri, int maxBytes) {
        try {
            InputStream input = getContentResolver().openInputStream(uri);
            if (input == null) return "";
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
                if (total > maxBytes) {
                    input.close();
                    return "";
                }
                out.write(buffer, 0, read);
            }
            input.close();
            return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP);
        } catch (Exception error) {
            return "";
        }
    }

    private void sendStatus() {
        try {
            JSONObject payload = baseDevicePayload();
            BatteryManager battery = (BatteryManager) getSystemService(BATTERY_SERVICE);
            payload.put("battery_percent", battery == null ? -1 : battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY));
            post("/android-companion/app/status", payload);
        } catch (Exception error) {
            log("Status failed: " + error.getMessage());
        }
    }

    private void sendLocation() {
        try {
            JSONObject payload = baseDevicePayload();
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
                LocationManager manager = (LocationManager) getSystemService(LOCATION_SERVICE);
                Location location = manager == null ? null : manager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
                if (location != null) {
                    payload.put("latitude", location.getLatitude());
                    payload.put("longitude", location.getLongitude());
                    payload.put("accuracy", location.getAccuracy());
                }
            }
            post("/android-companion/app/location", payload);
        } catch (Exception error) {
            log("Location failed: " + error.getMessage());
        }
    }

    private JSONObject baseDevicePayload() throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("device_id", Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID));
        payload.put("name", android.os.Build.MODEL);
        return payload;
    }

    private void post(String path, JSONObject payload) {
        new Thread(() -> {
            try {
                JSONObject result = FridayApi.post(this, path, payload);
                runOnUiThread(() -> log(result.optString("summary", result.toString())));
            } catch (Exception error) {
                runOnUiThread(() -> log(error.getMessage()));
            }
        }).start();
    }

    private void log(String message) {
        logView.append(message + "\n");
    }
}
