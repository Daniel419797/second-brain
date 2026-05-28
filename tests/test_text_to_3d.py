from types import SimpleNamespace

from core import text_to_3d


class FakeResponse:
    def __init__(self, status_code=200, data=None, content=b"data", text=""):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.content = content
        self.text = text

    def json(self):
        return self._data


class FakeRequests:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, timeout=60, **kwargs):
        self.posts.append((url, kwargs))
        if len(self.posts) == 1:
            return FakeResponse(data={"result": "preview-task"})
        return FakeResponse(data={"result": "refine-task"})

    def get(self, url, timeout=60, **kwargs):
        self.gets.append((url, kwargs))
        if url.endswith("/preview-task"):
            return FakeResponse(data={"id": "preview-task", "status": "SUCCEEDED", "model_urls": {"glb": "https://assets/model-preview.glb"}})
        if url.endswith("/refine-task"):
            return FakeResponse(
                data={
                    "id": "refine-task",
                    "status": "SUCCEEDED",
                    "model_urls": {
                        "glb": "https://assets/model.glb",
                        "obj": "https://assets/model.obj",
                        "mtl": "https://assets/model.mtl",
                    },
                    "thumbnail_url": "https://assets/preview.png",
                    "texture_urls": [{"base_color": "https://assets/base.png", "normal": "https://assets/normal.png"}],
                }
            )
        return FakeResponse(content=b"file-bytes")


class FakeTripoRequests:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, timeout=60, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(data={"data": {"task_id": "tripo-task"}})

    def get(self, url, timeout=60, **kwargs):
        self.gets.append((url, kwargs))
        if url.endswith("/tripo-task"):
            return FakeResponse(
                data={
                    "data": {
                        "task_id": "tripo-task",
                        "status": "success",
                        "output": {
                            "pbr_model": "https://tripo/model.glb",
                            "rendered_image": "https://tripo/render.png",
                        },
                    }
                }
            )
        return FakeResponse(content=b"asset")


def _fake_config(key, default=None):
    values = {
        "text_to_3d_enabled": True,
        "text_to_3d_timeout_seconds": 30,
        "text_to_3d_poll_seconds": 0.01,
        "text_to_3d_request_timeout_seconds": 10,
        "text_to_3d_download_timeout_seconds": 10,
        "text_to_3d_meshy_api_key_env": "MESHY_API_KEY",
        "text_to_3d_meshy_base_url": "https://api.meshy.test/openapi/v2/text-to-3d",
        "text_to_3d_meshy_ai_model": "meshy-6",
        "text_to_3d_meshy_model_type": "standard",
        "text_to_3d_meshy_refine_enabled": True,
        "text_to_3d_meshy_enable_pbr": True,
        "text_to_3d_meshy_should_remesh": True,
        "text_to_3d_meshy_target_polycount": 100000,
        "text_to_3d_meshy_auto_size": True,
        "text_to_3d_meshy_moderation": True,
        "text_to_3d_meshy_human_pose_mode": "a-pose",
        "text_to_3d_tripo_api_key_env": "TRIPO_API_KEY",
        "text_to_3d_tripo_base_url": "https://api.tripo.test/v2/openapi",
        "text_to_3d_tripo_model_version": "v3.1-20260211",
        "text_to_3d_tripo_texture": True,
        "text_to_3d_tripo_pbr": True,
        "text_to_3d_tripo_texture_quality": "detailed",
        "text_to_3d_tripo_geometry_quality": "detailed",
        "text_to_3d_tripo_auto_size": True,
        "text_to_3d_tripo_export_uv": True,
        "text_to_3d_tripo_face_limit": 0,
    }
    return values.get(key, default)


def test_meshy_backend_submits_refines_and_downloads(monkeypatch, tmp_path):
    fake_requests = FakeRequests()
    monkeypatch.setattr(text_to_3d, "config_value", _fake_config)
    monkeypatch.setattr(text_to_3d, "_requests", lambda: fake_requests)
    monkeypatch.setenv("MESHY_API_KEY", "test-key")

    result = text_to_3d.generate("photorealistic human character", tmp_path, provider="meshy", formats=["glb", "obj"])

    assert result["ok"] is True
    assert result["provider"] == "meshy"
    assert result["task_ids"] == {"preview": "preview-task", "refine": "refine-task"}
    assert {"glb", "obj", "mtl", "preview", "texture_0_base_color", "texture_0_normal"}.issubset(result["paths"])
    assert fake_requests.posts[0][1]["json"]["mode"] == "preview"
    assert fake_requests.posts[1][1]["json"]["mode"] == "refine"
    assert fake_requests.posts[1][1]["json"]["enable_pbr"] is True


def test_tripo_backend_submits_h3_detailed_pbr_and_downloads(monkeypatch, tmp_path):
    fake_requests = FakeTripoRequests()
    monkeypatch.setattr(text_to_3d, "config_value", _fake_config)
    monkeypatch.setattr(text_to_3d, "_requests", lambda: fake_requests)
    monkeypatch.setenv("TRIPO_API_KEY", "test-key")

    result = text_to_3d.generate("cinematic city", tmp_path, provider="tripo", formats=["glb"])

    assert result["ok"] is True
    assert result["provider"] == "tripo"
    assert result["task_ids"] == {"task": "tripo-task"}
    assert {"glb", "preview"}.issubset(result["paths"])
    body = fake_requests.posts[0][1]["json"]
    assert body["model_version"] == "v3.1-20260211"
    assert body["pbr"] is True
    assert body["texture_quality"] == "detailed"
    assert body["geometry_quality"] == "detailed"


def test_local_command_backend_reports_missing_command(monkeypatch, tmp_path):
    monkeypatch.setattr(
        text_to_3d,
        "config_value",
        lambda key, default=None: "missing-command --prompt {prompt}" if key == "text_to_3d_local_command" else _fake_config(key, default),
    )

    result = text_to_3d.generate("object", tmp_path, provider="local_command", formats=["glb"])

    assert result["ok"] is False
    assert "not found" in result["summary"]
