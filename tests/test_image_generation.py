from core import image_generation


class _FakeResponse:
    def __init__(self, status_code=200, content=b"\xff\xd8fake", content_type="image/jpeg", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text
        self.headers = {"content-type": content_type}

    def json(self):
        return {}


def test_image_generation_status_reports_unreachable_local(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.setattr(
        image_generation,
        "config_value",
        lambda key, default=None: "http://127.0.0.1:7860" if key == "stable_diffusion_url" else "" if key == "hf_token" else default,
    )
    monkeypatch.setattr(
        image_generation,
        "_stable_diffusion_probe",
        lambda url: {"reachable": False, "reason": "not reachable: connection refused"},
    )

    status = image_generation.status()

    assert status["ready"] is False
    assert status["local_stable_diffusion"]["configured"] is True
    assert status["local_stable_diffusion"]["reachable"] is False
    assert "connection refused" in status["local_stable_diffusion"]["reason"]


def test_image_generation_status_reports_pollinations_ready(monkeypatch):
    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "pollinations")
    monkeypatch.setattr(image_generation, "_pollinations_probe", lambda: {"reachable": True, "reason": "reachable"})
    monkeypatch.setattr(image_generation, "_stable_diffusion_probe", lambda url: {"reachable": False, "reason": "connection refused"})

    status = image_generation.status()

    assert status["ready"] is True
    assert status["provider"] == "pollinations"
    assert status["pollinations"]["configured"] is True
    assert status["pollinations"]["reachable"] is True


def test_image_generation_pollinations_saves_image(monkeypatch, tmp_path):
    monkeypatch.setattr(image_generation, "DB_PATH", tmp_path / "images.sqlite3")
    monkeypatch.setattr(image_generation, "OUTPUT_DIR", tmp_path / "generated")
    monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "pollinations")
    calls = []

    class FakeRequests:
        @staticmethod
        def get(url, params=None, timeout=None):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return _FakeResponse()

    monkeypatch.setattr(image_generation, "requests", FakeRequests)

    result = image_generation.generate_image("a small blue robot", provider="pollinations")

    assert result["ok"] is True
    assert result["provider"] == "pollinations"
    assert result["path"].endswith(".jpg")
    assert calls[0]["params"]["safe"] == "true"
    assert image_generation.list_images(limit=1)[0]["status"] == "generated"


def test_image_generation_reports_missing_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(image_generation, "DB_PATH", tmp_path / "images.sqlite3")
    monkeypatch.setattr(image_generation, "OUTPUT_DIR", tmp_path / "generated")
    monkeypatch.delenv("STABLE_DIFFUSION_URL", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    monkeypatch.setattr(
        image_generation,
        "config_value",
        lambda key, default=None: "" if key in {"stable_diffusion_url", "hf_token"} else default,
    )

    result = image_generation.generate_image("a friendly cat", provider="stable_diffusion")

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert "STABLE_DIFFUSION_URL" in result["reason"]
    assert image_generation.list_images(limit=1)[0]["prompt"] == "a friendly cat"


def test_image_generation_blocks_minor_explicit_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(image_generation, "DB_PATH", tmp_path / "images.sqlite3")
    monkeypatch.setattr(image_generation, "OUTPUT_DIR", tmp_path / "generated")

    result = image_generation.generate_image("explicit nude image of a child")

    assert result["status"] == "blocked"
    assert result["ok"] is False
