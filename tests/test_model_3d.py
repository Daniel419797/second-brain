import json
from pathlib import Path

from core import model_3d, model_3d_studio, text_to_3d
from tools import power_center


def _configure_model_dir(monkeypatch, tmp_path):
    def fake_config(key, default=None):
        values = {
            "model_3d_output_dir": str(tmp_path),
            "model_3d_default_formats": "obj,stl,gltf,glb",
            "model_3d_default_segments": 12,
            "model_3d_quality_default": "procedural",
        }
        return values.get(key, default)

    monkeypatch.setattr(model_3d, "config_value", fake_config)
    monkeypatch.setattr(model_3d_studio, "config_value", fake_config)


def test_model_3d_creates_real_mesh_exports(monkeypatch, tmp_path):
    _configure_model_dir(monkeypatch, tmp_path)

    result = model_3d.create_model("low poly spaceship as glb", formats=["obj", "stl", "gltf", "glb"])

    assert result["shape"] == "spaceship"
    assert result["vertices"] > 0
    assert result["faces"] > 0
    paths = result["paths"]
    assert set(paths) == {"obj", "stl", "gltf", "glb"}
    assert Path(paths["obj"]).read_text(encoding="utf-8").startswith("# Friday generated 3D model")
    assert Path(paths["stl"]).read_text(encoding="utf-8").startswith("solid")
    gltf = json.loads(Path(paths["gltf"]).read_text(encoding="utf-8"))
    assert gltf["asset"]["version"] == "2.0"
    assert gltf["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,")
    assert Path(paths["glb"]).read_bytes()[:4] == b"glTF"


def test_model_3d_can_export_single_format(monkeypatch, tmp_path):
    _configure_model_dir(monkeypatch, tmp_path)

    result = model_3d.create_model("sphere planet", formats="stl")

    assert result["shape"] == "sphere"
    assert list(result["paths"]) == ["stl"]
    assert Path(result["paths"]["stl"]).exists()


def test_model_3d_creates_complex_city_with_materials(monkeypatch, tmp_path):
    _configure_model_dir(monkeypatch, tmp_path)

    result = model_3d.create_model("complex 3d model of a city block", formats=["obj", "gltf", "glb"])

    assert result["shape"] == "city"
    assert result["complex"] is True
    assert result["vertices"] > 500
    assert result["faces"] > 700
    assert {"glass", "road", "ground"}.issubset(set(result["materials"]))
    obj_path = Path(result["paths"]["obj"])
    assert "mtllib" in obj_path.read_text(encoding="utf-8")
    assert obj_path.with_suffix(".mtl").exists()
    gltf = json.loads(Path(result["paths"]["gltf"]).read_text(encoding="utf-8"))
    assert len(gltf["materials"]) >= 4
    assert len(gltf["meshes"][0]["primitives"]) >= 4
    assert Path(result["paths"]["glb"]).read_bytes()[:4] == b"glTF"


def test_model_3d_creates_house_and_human(monkeypatch, tmp_path):
    _configure_model_dir(monkeypatch, tmp_path)

    house = model_3d.create_model("3d model of a house with garage", formats="gltf")
    human = model_3d.create_model("3d model of a human character", formats="gltf")

    assert house["shape"] == "house"
    assert house["complex"] is True
    assert {"walls", "roof", "glass", "door"}.issubset(set(house["materials"]))
    assert human["shape"] == "human"
    assert human["complex"] is True
    assert {"skin", "shirt", "pants", "eye"}.issubset(set(human["materials"]))


def test_power_center_model3d_action(monkeypatch, tmp_path):
    _configure_model_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(power_center, "_permission_reply", lambda inputs: "")

    reply = power_center.execute({"action": "model3d_create", "prompt": "3d model of a terrain island", "formats": ["obj"]})

    assert reply.startswith("3D model created")
    assert "OBJ:" in reply


def test_model_3d_studio_fallback_is_honest_without_blender(monkeypatch, tmp_path):
    def fake_config(key, default=None):
        values = {
            "model_3d_output_dir": str(tmp_path),
            "model_3d_default_formats": "obj,stl,gltf,glb",
            "model_3d_default_segments": 12,
            "model_3d_quality_default": "studio",
            "model_3d_blender_enabled": True,
            "model_3d_blender_path": "missing-blender",
            "model_3d_studio_default_formats": "glb,obj,preview",
            "model_3d_studio_render_preview": True,
            "model_3d_studio_fallback_procedural": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(model_3d, "config_value", fake_config)
    monkeypatch.setattr(model_3d_studio, "config_value", fake_config)
    monkeypatch.setattr(model_3d_studio.shutil, "which", lambda command: None)

    result = model_3d.create_model("photorealistic zbrush quality human", formats=["glb"])

    assert result["quality"] == "procedural_fallback"
    assert result["photorealistic_target"] is True
    assert result["studio"]["script"].endswith("studio_scene.py")
    assert Path(result["studio"]["script"]).exists()
    assert Path(result["paths"]["glb"]).read_bytes()[:4] == b"glTF"
    assert "needs a configured text-to-3D backend" in result["summary"]


def test_model_3d_studio_invokes_blender_when_available(monkeypatch, tmp_path):
    def fake_config(key, default=None):
        values = {
            "model_3d_output_dir": str(tmp_path),
            "model_3d_blender_enabled": True,
            "model_3d_blender_path": "blender",
            "model_3d_studio_default_formats": "glb,obj,preview",
            "model_3d_studio_render_preview": True,
            "model_3d_studio_timeout_seconds": 30,
        }
        return values.get(key, default)

    calls = []

    def fake_run_blender(blender, script_path, output_dir):
        calls.append((blender, script_path, output_dir))
        spec = json.loads((output_dir / "studio_spec.json").read_text(encoding="utf-8"))
        Path(spec["paths"]["blend"]).write_text("blend", encoding="utf-8")
        Path(spec["paths"]["glb"]).write_bytes(b"glTFmock")
        Path(spec["paths"]["obj"]).write_text("obj", encoding="utf-8")
        Path(spec["paths"]["preview"]).write_bytes(b"png")
        return {"ok": True, "stdout": "done", "stderr": ""}

    monkeypatch.setattr(model_3d_studio, "config_value", fake_config)
    monkeypatch.setattr(model_3d_studio.shutil, "which", lambda command: "C:/Blender/blender.exe")
    monkeypatch.setattr(model_3d_studio, "_run_blender", fake_run_blender)

    result = model_3d_studio.create_studio_model("photorealistic city", formats=["glb", "obj"])

    assert result["studio_ready"] is True
    assert calls
    assert set(result["paths"]) == {"blend", "glb", "obj", "preview"}
    assert result["summary"].startswith("Blender studio 3D model created")


def test_model_3d_studio_uses_text_to_3d_backend_without_blender(monkeypatch, tmp_path):
    source = tmp_path / "source.glb"
    source.write_bytes(b"glTFbackend")

    def fake_config(key, default=None):
        values = {
            "model_3d_output_dir": str(tmp_path),
            "model_3d_studio_use_text_to_3d": True,
            "model_3d_blender_enabled": True,
            "model_3d_blender_path": "missing-blender",
            "model_3d_studio_default_formats": "glb,obj,preview",
            "model_3d_studio_render_preview": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(model_3d_studio, "config_value", fake_config)
    monkeypatch.setattr(model_3d_studio.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        text_to_3d,
        "generate",
        lambda *args, **kwargs: {"ok": True, "provider": "meshy", "paths": {"glb": str(source)}, "summary": "backend ready"},
    )

    result = model_3d_studio.create_studio_model("photorealistic creature", formats=["glb"], backend="meshy")

    assert result["ok"] is True
    assert result["backend_ready"] is True
    assert result["studio_ready"] is False
    assert result["paths"] == {"glb": str(source)}
    assert result["text_to_3d"]["provider"] == "meshy"


def test_model_3d_studio_imports_text_to_3d_source_when_blender_runs(monkeypatch, tmp_path):
    source = tmp_path / "source.glb"
    source.write_bytes(b"glTFbackend")

    def fake_config(key, default=None):
        values = {
            "model_3d_output_dir": str(tmp_path),
            "model_3d_studio_use_text_to_3d": True,
            "model_3d_blender_enabled": True,
            "model_3d_blender_path": "blender",
            "model_3d_studio_default_formats": "glb,obj,preview",
            "model_3d_studio_render_preview": True,
            "model_3d_studio_timeout_seconds": 30,
        }
        return values.get(key, default)

    seen_specs = []

    def fake_run_blender(blender, script_path, output_dir):
        spec = json.loads((output_dir / "studio_spec.json").read_text(encoding="utf-8"))
        seen_specs.append(spec)
        Path(spec["paths"]["blend"]).write_text("blend", encoding="utf-8")
        Path(spec["paths"]["glb"]).write_bytes(b"glTFmock")
        return {"ok": True, "stdout": "done", "stderr": ""}

    monkeypatch.setattr(model_3d_studio, "config_value", fake_config)
    monkeypatch.setattr(model_3d_studio.shutil, "which", lambda command: "C:/Blender/blender.exe")
    monkeypatch.setattr(model_3d_studio, "_run_blender", fake_run_blender)
    monkeypatch.setattr(
        text_to_3d,
        "generate",
        lambda *args, **kwargs: {"ok": True, "provider": "tripo", "paths": {"glb": str(source)}, "summary": "backend ready"},
    )

    result = model_3d_studio.create_studio_model("photorealistic city", formats=["glb"], backend="tripo")

    assert result["studio_ready"] is True
    assert result["backend_ready"] is True
    assert seen_specs[0]["source_model"] == str(source)
