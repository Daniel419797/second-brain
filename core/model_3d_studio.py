"""Blender-backed studio pipeline for high-quality 3D assets."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ROOT_DIR, config_value


def create_studio_model(
    prompt: str,
    *,
    shape: str = "",
    formats: list[str] | tuple[str, ...] | str | None = None,
    name: str = "",
    backend: str = "",
) -> dict[str, Any]:
    clean_prompt = _clean(prompt)
    clean_name = _safe_name(name or clean_prompt)
    clean_shape = _shape(shape or clean_prompt)
    output_dir = _output_dir() / f"{clean_name}-{_now_slug()}-studio"
    output_dir.mkdir(parents=True, exist_ok=True)
    wanted = _formats(formats)
    text_to_3d_result: dict[str, Any] = {}
    source_model = ""
    if bool(config_value("model_3d_studio_use_text_to_3d", True)):
        from core import text_to_3d

        text_to_3d_result = text_to_3d.generate(
            clean_prompt,
            output_dir / "text_to_3d",
            formats=wanted,
            provider=backend,
            name=clean_name,
            shape=clean_shape,
        )
        source_model = _primary_model_path(text_to_3d_result.get("paths") or {})
    script_path = output_dir / "studio_scene.py"
    spec = {
        "prompt": clean_prompt,
        "shape": clean_shape,
        "name": clean_name,
        "formats": sorted(wanted),
        "paths": _expected_paths(output_dir, clean_name, wanted),
        "source_model": source_model,
        "text_to_3d": {
            "ok": bool(text_to_3d_result.get("ok")),
            "provider": text_to_3d_result.get("provider", ""),
            "paths": text_to_3d_result.get("paths", {}),
            "summary": text_to_3d_result.get("summary", ""),
        },
    }
    script_path.write_text(_blender_script(spec), encoding="utf-8")
    spec_path = output_dir / "studio_spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=True, indent=2), encoding="utf-8")

    blender = _blender_executable()
    if not blender:
        if text_to_3d_result.get("ok"):
            return _manifest(
                clean_prompt,
                clean_shape,
                clean_name,
                output_dir,
                script_path,
                spec_path,
                ok=True,
                studio_ready=False,
                backend_ready=True,
                paths=text_to_3d_result.get("paths") or {},
                setup_hint="Text-to-3D backend produced a model. Install/configure Blender for studio cleanup, .blend output, and rendered previews.",
                text_to_3d=text_to_3d_result,
            )
        manifest = _manifest(
            clean_prompt,
            clean_shape,
            clean_name,
            output_dir,
            script_path,
            spec_path,
            ok=False,
            studio_ready=False,
            backend_ready=False,
            paths={},
            setup_hint="Install Blender and set model_3d_blender_path to enable photorealistic/studio exports.",
            text_to_3d=text_to_3d_result,
        )
        return manifest

    run = _run_blender(blender, script_path, output_dir)
    paths = {key: path for key, path in spec["paths"].items() if Path(path).exists()}
    if not paths and text_to_3d_result.get("ok"):
        paths = text_to_3d_result.get("paths") or {}
    studio_ready = run["ok"] and any(key in paths for key in {"blend", "glb", "gltf", "obj", "stl", "preview"})
    ok = studio_ready or bool(text_to_3d_result.get("ok"))
    setup_hint = "" if studio_ready else (run.get("stderr") or run.get("stdout") or "Blender did not create the expected exports.")
    return _manifest(
        clean_prompt,
        clean_shape,
        clean_name,
        output_dir,
        script_path,
        spec_path,
        ok=ok,
        studio_ready=studio_ready,
        backend_ready=bool(text_to_3d_result.get("ok")),
        paths=paths,
        setup_hint=setup_hint,
        blender=blender,
        stdout=run.get("stdout", ""),
        stderr=run.get("stderr", ""),
        text_to_3d=text_to_3d_result,
    )


def _run_blender(blender: str, script_path: Path, output_dir: Path) -> dict[str, Any]:
    timeout = max(30, int(config_value("model_3d_studio_timeout_seconds", 180)))
    try:
        result = subprocess.run(
            [blender, "--background", "--python", str(script_path)],
            cwd=str(output_dir),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "Blender executable was not found."}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "stdout": "", "stderr": f"Blender timed out after {timeout} seconds: {exc}"}
    return {"ok": result.returncode == 0, "stdout": _bounded(result.stdout), "stderr": _bounded(result.stderr), "returncode": result.returncode}


def _manifest(
    prompt: str,
    shape: str,
    name: str,
    output_dir: Path,
    script_path: Path,
    spec_path: Path,
    *,
    ok: bool,
    studio_ready: bool,
    backend_ready: bool,
    paths: dict[str, str],
    setup_hint: str = "",
    blender: str = "",
    stdout: str = "",
    stderr: str = "",
    text_to_3d: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "ok": ok,
        "quality": "studio_blender",
        "photorealistic_target": True,
        "studio_ready": studio_ready,
        "backend_ready": backend_ready,
        "text_to_3d": text_to_3d or {},
        "prompt": prompt,
        "shape": shape,
        "name": name,
        "created_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "output_dir": str(output_dir),
        "script": str(script_path),
        "spec": str(spec_path),
        "paths": paths,
        "blender": blender,
        "stdout": stdout,
        "stderr": stderr,
        "setup_hint": setup_hint,
    }
    manifest["summary"] = _summary(manifest)
    manifest_path = output_dir / "studio_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    return manifest


def _summary(manifest: dict[str, Any]) -> str:
    paths = manifest.get("paths") or {}
    if manifest.get("studio_ready"):
        exports = " ".join(f"{fmt.upper()}: {path}" for fmt, path in paths.items())
        backend = manifest.get("text_to_3d") or {}
        provider_note = f" Source backend: {backend.get('provider')}." if backend.get("ok") else ""
        return f"Blender studio 3D model created for {manifest['shape']}.{provider_note} {exports}".strip()
    if manifest.get("backend_ready"):
        exports = " ".join(f"{fmt.upper()}: {path}" for fmt, path in paths.items())
        backend = manifest.get("text_to_3d") or {}
        return (
            f"Text-to-3D backend generated a real model with {backend.get('provider')}. "
            f"Blender studio cleanup/render is not ready yet. {exports} {manifest.get('setup_hint')}"
        ).strip()
    return (
        "Photorealistic/ZBrush-quality output needs a configured text-to-3D backend and Blender studio pipeline. "
        f"Created a Blender scene script instead: {manifest.get('script')}. {manifest.get('setup_hint')}"
    ).strip()


def _blender_executable() -> str:
    if not bool(config_value("model_3d_blender_enabled", True)):
        return ""
    configured = str(config_value("model_3d_blender_path", "blender") or "blender").strip()
    if not configured:
        return ""
    path = Path(configured).expanduser()
    if path.exists():
        return str(path)
    return shutil.which(configured) or ""


def _expected_paths(output_dir: Path, name: str, formats: set[str]) -> dict[str, str]:
    paths: dict[str, str] = {"blend": str(output_dir / f"{name}.blend")}
    if "glb" in formats:
        paths["glb"] = str(output_dir / f"{name}.glb")
    if "gltf" in formats:
        paths["gltf"] = str(output_dir / f"{name}.gltf")
    if "obj" in formats:
        paths["obj"] = str(output_dir / f"{name}.obj")
    if "stl" in formats:
        paths["stl"] = str(output_dir / f"{name}.stl")
    if bool(config_value("model_3d_studio_render_preview", True)):
        paths["preview"] = str(output_dir / f"{name}_preview.png")
    return paths


def _primary_model_path(paths: dict[str, str]) -> str:
    for key in ("glb", "gltf", "obj", "fbx", "stl", "usdz", "3mf"):
        path = str(paths.get(key) or "")
        if path and Path(path).exists():
            return path
    return ""


def _formats(formats: list[str] | tuple[str, ...] | str | None) -> set[str]:
    raw = formats if formats is not None else str(config_value("model_3d_studio_default_formats", "glb,obj,preview"))
    if isinstance(raw, str):
        items = [item.strip() for item in re.split(r"[, ]+", raw) if item.strip()]
    else:
        items = [str(item).strip() for item in raw if str(item).strip()]
    allowed = {"obj", "stl", "gltf", "glb", "preview", "blend"}
    wanted = {item.lower().lstrip(".") for item in items}
    return wanted & allowed or {"glb", "obj", "preview"}


def _blender_script(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=True)
    return f'''# Auto-generated by Friday's Blender studio pipeline.
import json
import math
from pathlib import Path

import bpy

SPEC = json.loads({payload!r})
PATHS = SPEC["paths"]


def clean_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def mat(name, color, roughness=0.72, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return material


MATS = {{}}


def material(name, color, roughness=0.72, metallic=0.0):
    key = (name, tuple(color), roughness, metallic)
    if key not in MATS:
        MATS[key] = mat(name, color, roughness, metallic)
    return MATS[key]


def cube(name, loc, scale, material_name, color, bevel=0.02):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material(material_name, color))
    if bevel:
        mod = obj.modifiers.new("soft_bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    return obj


def sphere(name, loc, scale, material_name, color, segments=48):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(16, segments // 2), location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material(material_name, color))
    bpy.ops.object.shade_smooth()
    return obj


def cylinder(name, loc, radius, depth, material_name, color, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material(material_name, color))
    bpy.ops.object.shade_smooth()
    obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    return obj


def roof(name, center, width, depth, height, material_name, color):
    cx, cy, cz = center
    verts = [
        (-width/2, -depth/2, 0), (width/2, -depth/2, 0), (0, -depth/2, height),
        (-width/2, depth/2, 0), (width/2, depth/2, 0), (0, depth/2, height),
    ]
    faces = [(0,1,2), (3,5,4), (0,2,5,3), (1,4,5,2), (0,3,4,1)]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (cx, cy, cz)
    obj.data.materials.append(material(material_name, color))
    obj.modifiers.new("roof_bevel", "BEVEL").width = 0.025
    obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    return obj


def add_lights_and_camera():
    bpy.ops.object.light_add(type="AREA", location=(0, -5, 7))
    key = bpy.context.object
    key.name = "large_softbox_key"
    key.data.energy = 650
    key.data.size = 5
    bpy.ops.object.light_add(type="SUN", location=(2, -4, 7))
    sun = bpy.context.object
    sun.name = "warm_sun"
    sun.data.energy = 1.8
    bpy.ops.object.camera_add(location=(5, -7, 4.2), rotation=(math.radians(62), 0, math.radians(38)))
    bpy.context.scene.camera = bpy.context.object
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.eevee.taa_render_samples = 64 if hasattr(bpy.context.scene, "eevee") else 16
    try:
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles.samples = 96
    except Exception:
        pass


def import_source_model():
    source = SPEC.get("source_model") or ""
    if not source:
        return False
    suffix = Path(source).suffix.lower()
    before = set(bpy.context.scene.objects)
    try:
        if suffix in [".glb", ".gltf"]:
            bpy.ops.import_scene.gltf(filepath=source)
        elif suffix == ".obj":
            try:
                bpy.ops.wm.obj_import(filepath=source)
            except Exception:
                bpy.ops.import_scene.obj(filepath=source)
        elif suffix == ".stl":
            try:
                bpy.ops.wm.stl_import(filepath=source)
            except Exception:
                bpy.ops.import_mesh.stl(filepath=source)
        else:
            return False
    except Exception:
        return False
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    for obj in imported:
        obj.name = "text_to_3d_" + obj.name
        if obj.type == "MESH":
            try:
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.shade_smooth()
                obj.modifiers.new("studio_weighted_normals", "WEIGHTED_NORMAL")
                obj.select_set(False)
            except Exception:
                pass
    return bool(imported)


def build_city():
    cube("asphalt_road_x", (0, 0, 0.015), (8.5, 0.7, 0.03), "wet asphalt", (0.015, 0.016, 0.018, 1), 0.01)
    cube("asphalt_road_y", (0, 0, 0.02), (0.7, 8.5, 0.03), "wet asphalt", (0.015, 0.016, 0.018, 1), 0.01)
    cube("city_base", (0, 0, -0.04), (8.8, 8.8, 0.08), "urban grass", (0.13, 0.34, 0.14, 1), 0.0)
    slots = [-3.0, -1.55, 1.55, 3.0]
    for ix, x in enumerate(slots):
        for iy, y in enumerate(slots):
            h = 0.9 + ((ix * 7 + iy * 3) % 8) * 0.28
            w = 0.72 + (ix % 2) * 0.16
            d = 0.68 + (iy % 2) * 0.16
            cube(f"beveled_tower_{{ix}}_{{iy}}", (x, y, h/2), (w, d, h), "concrete facade", (0.46 + ix*0.025, 0.49, 0.51 + iy*0.02, 1), 0.035)
            cube(f"dark_roof_{{ix}}_{{iy}}", (x, y, h+0.035), (w*0.9, d*0.9, 0.07), "dark roof membrane", (0.04, 0.045, 0.05, 1), 0.018)
            rows = max(2, int(h / 0.23))
            for row in range(rows):
                z = 0.25 + row * 0.21
                for side in [-1, 1]:
                    cube(f"front_window_{{ix}}_{{iy}}_{{row}}_{{side}}", (x + side*w*0.22, y-d/2-0.015, z), (0.13, 0.02, 0.095), "blue reflective glass", (0.12, 0.44, 0.72, 1), 0.004)
                    cube(f"back_window_{{ix}}_{{iy}}_{{row}}_{{side}}", (x + side*w*0.22, y+d/2+0.015, z), (0.13, 0.02, 0.095), "blue reflective glass", (0.12, 0.44, 0.72, 1), 0.004)
            if (ix + iy) % 2 == 0:
                cylinder(f"tree_trunk_{{ix}}_{{iy}}", (x+0.55, y-0.55, 0.28), 0.055, 0.56, "bark", (0.22, 0.11, 0.045, 1), 16)
                sphere(f"tree_canopy_{{ix}}_{{iy}}", (x+0.55, y-0.55, 0.78), (0.32, 0.32, 0.34), "leaf canopy", (0.06, 0.28, 0.08, 1), 24)


def build_house():
    cube("grass_lawn", (0, 0, -0.03), (5.5, 4.8, 0.06), "short grass", (0.12, 0.38, 0.12, 1), 0)
    cube("stucco_walls", (0, 0, 0.72), (2.1, 1.55, 1.44), "warm stucco", (0.74, 0.63, 0.50, 1), 0.035)
    roof("clay_tile_roof", (0, 0, 1.44), 2.55, 1.9, 0.72, "terracotta roof", (0.52, 0.13, 0.08, 1))
    for i in range(7):
        cube(f"roof_tile_strip_{{i}}", (-1.05 + i*0.35, -0.97, 1.65), (0.035, 0.08, 0.55), "terracotta roof", (0.52, 0.13, 0.08, 1), 0.008)
    cube("wood_front_door", (0, -0.80, 0.42), (0.42, 0.05, 0.84), "varnished wood", (0.24, 0.11, 0.045, 1), 0.018)
    for x in [-0.65, 0.65]:
        cube(f"front_window_{{x}}", (x, -0.82, 0.88), (0.38, 0.04, 0.34), "glass panes", (0.30, 0.62, 0.82, 1), 0.01)
        cube(f"window_trim_{{x}}", (x, -0.845, 0.88), (0.46, 0.035, 0.42), "white trim", (0.88, 0.86, 0.78, 1), 0.006)
    cube("stone_path", (0, -1.65, 0.015), (0.58, 1.6, 0.03), "stone path", (0.45, 0.43, 0.39, 1), 0.02)
    cylinder("chimney", (0.68, 0.35, 1.92), 0.14, 0.65, "brick chimney", (0.40, 0.16, 0.10, 1), 12)
    cube("garage", (1.8, 0.1, 0.48), (1.15, 1.2, 0.96), "painted garage", (0.66, 0.63, 0.56, 1), 0.03)
    roof("garage_roof", (1.8, 0.1, 0.96), 1.35, 1.42, 0.38, "terracotta roof", (0.52, 0.13, 0.08, 1))


def build_human():
    skin = (0.69, 0.48, 0.36, 1)
    sphere("head", (0, -0.02, 2.25), (0.33, 0.30, 0.38), "skin shader", skin, 64)
    cylinder("neck", (0, 0, 1.86), 0.13, 0.26, "skin shader", skin, 32)
    cube("shirt_torso", (0, 0, 1.35), (0.74, 0.42, 0.96), "fabric shirt", (0.08, 0.38, 0.58, 1), 0.08)
    cube("pelvis", (0, 0, 0.79), (0.62, 0.36, 0.28), "denim", (0.08, 0.16, 0.34, 1), 0.05)
    for side in [-1, 1]:
        cube(f"arm_{{side}}", (side*0.54, 0, 1.30), (0.18, 0.24, 0.86), "skin shader", skin, 0.08)
        sphere(f"hand_{{side}}", (side*0.54, -0.01, 0.79), (0.12, 0.105, 0.12), "skin shader", skin, 32)
        cube(f"leg_{{side}}", (side*0.19, 0, 0.28), (0.25, 0.25, 0.86), "denim", (0.08, 0.16, 0.34, 1), 0.06)
        cube(f"shoe_{{side}}", (side*0.19, -0.11, -0.16), (0.31, 0.52, 0.16), "matte shoe leather", (0.025, 0.022, 0.02, 1), 0.04)
        sphere(f"eye_{{side}}", (side*0.105, -0.292, 2.31), (0.035, 0.018, 0.026), "dark eyes", (0.01, 0.008, 0.006, 1), 16)
    cube("mouth", (0, -0.31, 2.13), (0.17, 0.018, 0.025), "mouth color", (0.40, 0.06, 0.05, 1), 0.01)
    # Hair cap
    sphere("hair_mass", (0, 0.035, 2.42), (0.34, 0.31, 0.18), "dark hair", (0.035, 0.022, 0.014, 1), 48)


def build_default():
    if SPEC["shape"] == "city":
        build_city()
    elif SPEC["shape"] == "house":
        build_house()
    elif SPEC["shape"] == "human":
        build_human()
    else:
        build_house()


def export_outputs():
    Path(PATHS["blend"]).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=PATHS["blend"])
    if "glb" in PATHS:
        bpy.ops.export_scene.gltf(filepath=PATHS["glb"], export_format="GLB")
    if "gltf" in PATHS:
        bpy.ops.export_scene.gltf(filepath=PATHS["gltf"], export_format="GLTF_SEPARATE")
    if "obj" in PATHS:
        try:
            bpy.ops.wm.obj_export(filepath=PATHS["obj"])
        except Exception:
            bpy.ops.export_scene.obj(filepath=PATHS["obj"])
    if "stl" in PATHS:
        try:
            bpy.ops.wm.stl_export(filepath=PATHS["stl"])
        except Exception:
            bpy.ops.export_mesh.stl(filepath=PATHS["stl"])
    if "preview" in PATHS:
        bpy.context.scene.render.filepath = PATHS["preview"]
        bpy.ops.render.render(write_still=True)


clean_scene()
if not import_source_model():
    build_default()
add_lights_and_camera()
export_outputs()
'''


def _shape(value: str) -> str:
    lowered = str(value or "").lower()
    if re.search(r"\b(?:city|cities|urban|downtown|town|street\s+block|skyline|skyscrapers?)\b", lowered):
        return "city"
    if re.search(r"\b(?:human|person|people|man|woman|character|humanoid|avatar)\b", lowered):
        return "human"
    if re.search(r"\b(?:house|home|cottage|villa|bungalow|mansion|residential)\b", lowered):
        return "house"
    return str(value or "").strip() or "house"


def _output_dir() -> Path:
    raw = str(config_value("model_3d_output_dir", str(DATA_DIR / "3d_models")) or "").strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").lower()).strip(".-")
    return cleaned[:48] or "studio-model"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,.!?:;")


def _now_slug() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")


def _bounded(text: str, limit: int = 6000) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[:limit].rstrip() + "\n... truncated ..."
