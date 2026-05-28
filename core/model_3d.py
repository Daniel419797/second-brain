"""Procedural 3D model generation and real mesh exporters."""

from __future__ import annotations

import base64
import datetime as dt
import json
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ROOT_DIR, config_value

Vec3 = tuple[float, float, float]
Face = tuple[int, int, int]


@dataclass(frozen=True)
class Mesh:
    name: str
    vertices: list[Vec3]
    faces: list[Face]
    materials: dict[str, tuple[float, float, float, float]] = field(default_factory=lambda: {"default": (0.74, 0.78, 0.82, 1.0)})
    face_materials: list[str] = field(default_factory=list)


def create_model(
    prompt: str,
    *,
    shape: str = "",
    formats: list[str] | tuple[str, ...] | str | None = None,
    name: str = "",
    quality: str = "",
    backend: str = "",
) -> dict[str, Any]:
    clean_prompt = _clean(prompt)
    if not clean_prompt:
        raise ValueError("prompt is required")
    quality_mode = _quality(quality or clean_prompt)
    if quality_mode == "studio":
        from core import model_3d_studio

        studio = model_3d_studio.create_studio_model(clean_prompt, shape=shape, formats=formats, name=name, backend=backend)
        if studio.get("studio_ready") or not bool(config_value("model_3d_studio_fallback_procedural", True)):
            return studio
        fallback = _create_procedural_model(clean_prompt, shape=shape, formats=formats, name=name)
        fallback["quality"] = "procedural_fallback"
        fallback["photorealistic_target"] = True
        fallback["studio"] = {
            "script": studio.get("script"),
            "manifest": studio.get("manifest"),
            "setup_hint": studio.get("setup_hint"),
            "summary": studio.get("summary"),
        }
        fallback["summary"] = (
            f"{studio.get('summary')} Procedural fallback also created: "
            + " ".join(f"{fmt.upper()}: {path}" for fmt, path in (fallback.get("paths") or {}).items())
        ).strip()
        return fallback
    return _create_procedural_model(clean_prompt, shape=shape, formats=formats, name=name)


def _create_procedural_model(
    clean_prompt: str,
    *,
    shape: str = "",
    formats: list[str] | tuple[str, ...] | str | None = None,
    name: str = "",
) -> dict[str, Any]:
    model_shape = _shape(shape or clean_prompt)
    mesh = _mesh_for(model_shape, _safe_name(name or clean_prompt), clean_prompt)
    output_dir = _output_dir() / f"{_safe_name(name or clean_prompt)}-{_now_slug()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = export_mesh(mesh, output_dir / mesh.name, formats=formats)
    manifest = {
        "prompt": clean_prompt,
        "shape": model_shape,
        "name": mesh.name,
        "created_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "quality": "procedural",
        "photorealistic_target": False,
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "materials": sorted(mesh.materials),
        "complex": model_shape in {"city", "house", "human"},
        "formats": sorted(paths),
        "paths": paths,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    manifest["summary"] = _summary(manifest)
    return manifest


def export_mesh(mesh: Mesh, output_base: str | Path, *, formats: list[str] | tuple[str, ...] | str | None = None) -> dict[str, str]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    wanted = _formats(formats)
    paths: dict[str, str] = {}
    if "obj" in wanted:
        path = base.with_suffix(".obj")
        if mesh.materials:
            path.with_suffix(".mtl").write_text(_mtl(mesh), encoding="utf-8")
        path.write_text(_obj(mesh, mtl_name=path.with_suffix(".mtl").name if mesh.materials else ""), encoding="utf-8")
        paths["obj"] = str(path)
    if "stl" in wanted:
        path = base.with_suffix(".stl")
        path.write_text(_stl(mesh), encoding="utf-8")
        paths["stl"] = str(path)
    if "gltf" in wanted:
        path = base.with_suffix(".gltf")
        path.write_text(json.dumps(_gltf(mesh, embed=True), ensure_ascii=True, indent=2), encoding="utf-8")
        paths["gltf"] = str(path)
    if "glb" in wanted:
        path = base.with_suffix(".glb")
        path.write_bytes(_glb(mesh))
        paths["glb"] = str(path)
    return paths


def _mesh_for(shape: str, name: str, prompt: str) -> Mesh:
    segments = max(8, min(int(config_value("model_3d_default_segments", 24)), 64))
    if shape == "city":
        return _city(name)
    if shape == "house":
        return _house(name)
    if shape == "human":
        return _human(name, segments=segments)
    if shape == "sphere":
        return _apply_material(_sphere(name, segments=segments), "surface", (0.36, 0.57, 0.9, 1.0))
    if shape == "cylinder":
        return _apply_material(_cylinder(name, segments=segments), "surface", (0.64, 0.68, 0.72, 1.0))
    if shape == "cone":
        return _apply_material(_cone(name, segments=segments), "surface", (0.78, 0.58, 0.34, 1.0))
    if shape == "terrain":
        return _apply_material(_terrain(name), "terrain", (0.25, 0.55, 0.28, 1.0))
    if shape == "spaceship":
        return _spaceship(name)
    return _apply_material(_cube(name, elongated="building" in prompt.lower() or "tower" in prompt.lower()), "surface", (0.74, 0.78, 0.82, 1.0))


def _city(name: str) -> Mesh:
    parts: list[Mesh] = [
        _box("ground", (7.5, 7.5, 0.08), (0.0, 0.0, -0.04), "ground", (0.20, 0.46, 0.24, 1.0)),
        _box("main-road-x", (7.6, 0.55, 0.04), (0.0, 0.0, 0.02), "road", (0.07, 0.08, 0.09, 1.0)),
        _box("main-road-y", (0.55, 7.6, 0.04), (0.0, 0.0, 0.025), "road", (0.07, 0.08, 0.09, 1.0)),
    ]
    slots = [-2.7, -1.3, 1.3, 2.7]
    for ix, x in enumerate(slots):
        for iy, y in enumerate(slots):
            height = 0.75 + ((ix * 3 + iy * 5) % 7) * 0.22
            width = 0.58 + (ix % 2) * 0.12
            depth = 0.56 + (iy % 2) * 0.12
            material = f"building-{(ix + iy) % 3}"
            color = [(0.52, 0.59, 0.66, 1.0), (0.63, 0.58, 0.50, 1.0), (0.42, 0.51, 0.61, 1.0)][(ix + iy) % 3]
            parts.append(_box(f"building-{ix}-{iy}", (width, depth, height), (x, y, height / 2), material, color))
            parts.append(_box(f"roof-{ix}-{iy}", (width * 0.92, depth * 0.92, 0.06), (x, y, height + 0.03), "roof", (0.12, 0.13, 0.15, 1.0)))
            rows = max(1, int(height / 0.28))
            for row in range(rows):
                z = 0.22 + row * 0.24
                for side in (-1, 1):
                    parts.append(_box(f"window-f-{ix}-{iy}-{row}-{side}", (0.11, 0.02, 0.10), (x + side * width * 0.22, y - depth / 2 - 0.012, z), "glass", (0.36, 0.67, 0.92, 1.0)))
                    parts.append(_box(f"window-b-{ix}-{iy}-{row}-{side}", (0.11, 0.02, 0.10), (x + side * width * 0.22, y + depth / 2 + 0.012, z), "glass", (0.36, 0.67, 0.92, 1.0)))
            if (ix + iy) % 2 == 0:
                parts.extend(_tree(f"tree-{ix}-{iy}", x + 0.48, y - 0.48))
    parts.extend(
        [
            _box("crosswalk-a", (0.50, 0.04, 0.01), (-0.34, -0.34, 0.055), "marking", (0.92, 0.92, 0.82, 1.0)),
            _box("crosswalk-b", (0.50, 0.04, 0.01), (0.34, 0.34, 0.055), "marking", (0.92, 0.92, 0.82, 1.0)),
            _box("plaza", (0.72, 0.72, 0.03), (0.95, -0.95, 0.055), "plaza", (0.48, 0.43, 0.36, 1.0)),
        ]
    )
    return _merge(name, parts)


def _house(name: str) -> Mesh:
    parts = [
        _box("yard", (5.0, 4.0, 0.06), (0.0, 0.0, -0.03), "grass", (0.22, 0.52, 0.25, 1.0)),
        _box("walls", (2.0, 1.5, 1.25), (0.0, 0.0, 0.625), "walls", (0.78, 0.68, 0.55, 1.0)),
        _roof("gable-roof", (2.35, 1.82, 0.65), (0.0, 0.0, 1.25), "roof", (0.55, 0.12, 0.10, 1.0)),
        _box("front-door", (0.36, 0.04, 0.70), (0.0, -0.77, 0.35), "door", (0.32, 0.16, 0.08, 1.0)),
        _box("door-knob", (0.04, 0.02, 0.04), (0.13, -0.80, 0.35), "trim", (0.95, 0.78, 0.26, 1.0)),
        _box("left-window", (0.34, 0.04, 0.30), (-0.62, -0.78, 0.72), "glass", (0.42, 0.72, 0.95, 1.0)),
        _box("right-window", (0.34, 0.04, 0.30), (0.62, -0.78, 0.72), "glass", (0.42, 0.72, 0.95, 1.0)),
        _box("side-window", (0.04, 0.34, 0.28), (1.02, 0.28, 0.76), "glass", (0.42, 0.72, 0.95, 1.0)),
        _box("chimney", (0.25, 0.25, 0.65), (0.66, 0.34, 1.72), "chimney", (0.44, 0.22, 0.16, 1.0)),
        _box("porch", (0.92, 0.48, 0.12), (0.0, -1.08, 0.06), "porch", (0.50, 0.42, 0.34, 1.0)),
        _box("path", (0.52, 1.80, 0.025), (0.0, -1.85, 0.01), "path", (0.56, 0.53, 0.47, 1.0)),
        _box("garage", (1.15, 1.20, 0.90), (1.80, 0.12, 0.45), "garage", (0.70, 0.66, 0.58, 1.0)),
        _roof("garage-roof", (1.35, 1.38, 0.38), (1.80, 0.12, 0.90), "roof", (0.55, 0.12, 0.10, 1.0)),
        _box("garage-door", (0.78, 0.04, 0.48), (1.80, -0.50, 0.30), "door", (0.36, 0.33, 0.29, 1.0)),
    ]
    parts.extend(_tree("front-tree", -1.85, -1.15))
    return _merge(name, parts)


def _human(name: str, *, segments: int) -> Mesh:
    skin = (0.72, 0.50, 0.38, 1.0)
    denim = (0.12, 0.25, 0.48, 1.0)
    shirt = (0.18, 0.48, 0.62, 1.0)
    parts = [
        _box("torso", (0.68, 0.38, 0.95), (0.0, 0.0, 1.45), "shirt", shirt),
        _box("pelvis", (0.62, 0.34, 0.28), (0.0, 0.0, 0.84), "pants", denim),
        _transformed(_apply_material(_sphere("head", segments=max(8, segments // 2)), "skin", skin), scale=(0.34, 0.30, 0.38), offset=(0.0, -0.02, 2.25)),
        _transformed(_apply_material(_cylinder("neck", segments=8), "skin", skin), scale=(0.12, 0.12, 0.16), offset=(0.0, 0.0, 1.88)),
        _box("left-arm", (0.18, 0.22, 0.88), (-0.52, 0.0, 1.34), "skin", skin),
        _box("right-arm", (0.18, 0.22, 0.88), (0.52, 0.0, 1.34), "skin", skin),
        _box("left-hand", (0.20, 0.22, 0.18), (-0.52, 0.0, 0.82), "skin", skin),
        _box("right-hand", (0.20, 0.22, 0.18), (0.52, 0.0, 0.82), "skin", skin),
        _box("left-leg", (0.24, 0.24, 0.78), (-0.20, 0.0, 0.34), "pants", denim),
        _box("right-leg", (0.24, 0.24, 0.78), (0.20, 0.0, 0.34), "pants", denim),
        _box("left-foot", (0.30, 0.48, 0.14), (-0.20, -0.11, -0.11), "shoe", (0.08, 0.07, 0.06, 1.0)),
        _box("right-foot", (0.30, 0.48, 0.14), (0.20, -0.11, -0.11), "shoe", (0.08, 0.07, 0.06, 1.0)),
        _box("left-eye", (0.055, 0.025, 0.035), (-0.11, -0.315, 2.30), "eye", (0.03, 0.03, 0.03, 1.0)),
        _box("right-eye", (0.055, 0.025, 0.035), (0.11, -0.315, 2.30), "eye", (0.03, 0.03, 0.03, 1.0)),
        _box("mouth", (0.16, 0.02, 0.025), (0.0, -0.32, 2.12), "mouth", (0.42, 0.08, 0.08, 1.0)),
    ]
    return _merge(name, parts)


def _tree(name: str, x: float, y: float) -> list[Mesh]:
    return [
        _transformed(_apply_material(_cylinder(f"{name}-trunk", segments=8), "wood", (0.33, 0.18, 0.08, 1.0)), scale=(0.07, 0.07, 0.32), offset=(x, y, 0.34)),
        _transformed(_apply_material(_sphere(f"{name}-crown", segments=8), "leaves", (0.16, 0.43, 0.18, 1.0)), scale=(0.34, 0.34, 0.38), offset=(x, y, 0.88)),
    ]


def _box(name: str, size: Vec3, center: Vec3, material: str, color: tuple[float, float, float, float]) -> Mesh:
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    cx, cy, cz = center
    vertices = [
        (cx - sx, cy - sy, cz - sz),
        (cx + sx, cy - sy, cz - sz),
        (cx + sx, cy + sy, cz - sz),
        (cx - sx, cy + sy, cz - sz),
        (cx - sx, cy - sy, cz + sz),
        (cx + sx, cy - sy, cz + sz),
        (cx + sx, cy + sy, cz + sz),
        (cx - sx, cy + sy, cz + sz),
    ]
    faces = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 4),
        (3, 4, 0),
    ]
    return Mesh(name, vertices, faces, {material: color}, [material] * len(faces))


def _roof(name: str, size: Vec3, center: Vec3, material: str, color: tuple[float, float, float, float]) -> Mesh:
    width, depth, height = size
    cx, cy, cz = center
    z0 = cz
    z1 = cz + height
    vertices = [
        (cx - width / 2, cy - depth / 2, z0),
        (cx + width / 2, cy - depth / 2, z0),
        (cx, cy - depth / 2, z1),
        (cx - width / 2, cy + depth / 2, z0),
        (cx + width / 2, cy + depth / 2, z0),
        (cx, cy + depth / 2, z1),
    ]
    faces = [
        (0, 1, 2),
        (3, 5, 4),
        (0, 2, 5),
        (0, 5, 3),
        (1, 4, 5),
        (1, 5, 2),
        (0, 3, 4),
        (0, 4, 1),
    ]
    return Mesh(name, vertices, faces, {material: color}, [material] * len(faces))


def _merge(name: str, meshes: list[Mesh]) -> Mesh:
    vertices: list[Vec3] = []
    faces: list[Face] = []
    materials: dict[str, tuple[float, float, float, float]] = {}
    face_materials: list[str] = []
    offset = 0
    for mesh in meshes:
        vertices.extend(mesh.vertices)
        faces.extend((a + offset, b + offset, c + offset) for a, b, c in mesh.faces)
        materials.update(mesh.materials or {"default": (0.74, 0.78, 0.82, 1.0)})
        face_materials.extend(_face_materials(mesh))
        offset += len(mesh.vertices)
    return Mesh(name, vertices, faces, materials or {"default": (0.74, 0.78, 0.82, 1.0)}, face_materials)


def _transformed(mesh: Mesh, *, scale: Vec3 = (1.0, 1.0, 1.0), offset: Vec3 = (0.0, 0.0, 0.0), rotate_z: float = 0.0) -> Mesh:
    cos_z = math.cos(rotate_z)
    sin_z = math.sin(rotate_z)
    vertices: list[Vec3] = []
    for x, y, z in mesh.vertices:
        sx, sy, sz = x * scale[0], y * scale[1], z * scale[2]
        rx = sx * cos_z - sy * sin_z
        ry = sx * sin_z + sy * cos_z
        vertices.append((rx + offset[0], ry + offset[1], sz + offset[2]))
    return Mesh(mesh.name, vertices, list(mesh.faces), dict(mesh.materials), list(_face_materials(mesh)))


def _apply_material(mesh: Mesh, material: str, color: tuple[float, float, float, float]) -> Mesh:
    return Mesh(mesh.name, list(mesh.vertices), list(mesh.faces), {material: color}, [material] * len(mesh.faces))


def _face_materials(mesh: Mesh) -> list[str]:
    if len(mesh.face_materials) == len(mesh.faces):
        return list(mesh.face_materials)
    default = next(iter(mesh.materials or {"default": (0.74, 0.78, 0.82, 1.0)}))
    return [default] * len(mesh.faces)


def _cube(name: str, *, elongated: bool = False) -> Mesh:
    sx, sy, sz = (0.8, 0.8, 1.8) if elongated else (1.0, 1.0, 1.0)
    vertices = [
        (-sx, -sy, -sz),
        (sx, -sy, -sz),
        (sx, sy, -sz),
        (-sx, sy, -sz),
        (-sx, -sy, sz),
        (sx, -sy, sz),
        (sx, sy, sz),
        (-sx, sy, sz),
    ]
    faces = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 4),
        (3, 4, 0),
    ]
    return Mesh(name, vertices, faces)


def _sphere(name: str, *, segments: int) -> Mesh:
    rings = max(4, segments // 2)
    vertices: list[Vec3] = [(0.0, 0.0, 1.0)]
    for ring in range(1, rings):
        phi = math.pi * ring / rings
        z = math.cos(phi)
        radius = math.sin(phi)
        for seg in range(segments):
            theta = 2 * math.pi * seg / segments
            vertices.append((radius * math.cos(theta), radius * math.sin(theta), z))
    vertices.append((0.0, 0.0, -1.0))
    bottom = len(vertices) - 1
    faces: list[Face] = []
    first_ring = 1
    for seg in range(segments):
        faces.append((0, first_ring + seg, first_ring + ((seg + 1) % segments)))
    for ring in range(rings - 2):
        start = 1 + ring * segments
        nxt = start + segments
        for seg in range(segments):
            a = start + seg
            b = start + ((seg + 1) % segments)
            c = nxt + seg
            d = nxt + ((seg + 1) % segments)
            faces.append((a, c, b))
            faces.append((b, c, d))
    last_ring = 1 + (rings - 2) * segments
    for seg in range(segments):
        faces.append((bottom, last_ring + ((seg + 1) % segments), last_ring + seg))
    return Mesh(name, vertices, faces)


def _cylinder(name: str, *, segments: int) -> Mesh:
    vertices: list[Vec3] = [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]
    for z in (1.0, -1.0):
        for seg in range(segments):
            theta = 2 * math.pi * seg / segments
            vertices.append((math.cos(theta), math.sin(theta), z))
    top = 2
    bottom = 2 + segments
    faces: list[Face] = []
    for seg in range(segments):
        n = (seg + 1) % segments
        faces.append((0, top + n, top + seg))
        faces.append((1, bottom + seg, bottom + n))
        faces.append((top + seg, top + n, bottom + seg))
        faces.append((top + n, bottom + n, bottom + seg))
    return Mesh(name, vertices, faces)


def _cone(name: str, *, segments: int) -> Mesh:
    vertices: list[Vec3] = [(0.0, 0.0, 1.2), (0.0, 0.0, -1.0)]
    for seg in range(segments):
        theta = 2 * math.pi * seg / segments
        vertices.append((math.cos(theta), math.sin(theta), -1.0))
    base = 2
    faces: list[Face] = []
    for seg in range(segments):
        n = (seg + 1) % segments
        faces.append((0, base + seg, base + n))
        faces.append((1, base + n, base + seg))
    return Mesh(name, vertices, faces)


def _terrain(name: str) -> Mesh:
    size = 9
    vertices: list[Vec3] = []
    for y in range(size):
        for x in range(size):
            nx = (x / (size - 1)) * 2.0 - 1.0
            ny = (y / (size - 1)) * 2.0 - 1.0
            z = 0.18 * math.sin(nx * math.pi * 2) + 0.12 * math.cos(ny * math.pi * 3)
            vertices.append((nx, ny, z))
    faces: list[Face] = []
    for y in range(size - 1):
        for x in range(size - 1):
            a = y * size + x
            b = a + 1
            c = a + size
            d = c + 1
            faces.append((a, c, b))
            faces.append((b, c, d))
    return Mesh(name, vertices, faces)


def _spaceship(name: str) -> Mesh:
    vertices: list[Vec3] = [
        (0.0, 1.8, 0.0),
        (-0.45, 0.7, 0.28),
        (0.45, 0.7, 0.28),
        (0.45, 0.7, -0.28),
        (-0.45, 0.7, -0.28),
        (-0.55, -1.0, 0.22),
        (0.55, -1.0, 0.22),
        (0.55, -1.0, -0.22),
        (-0.55, -1.0, -0.22),
        (0.0, -1.45, 0.0),
        (-1.35, -0.45, -0.04),
        (-0.55, -0.25, -0.08),
        (-0.7, -0.95, -0.08),
        (1.35, -0.45, -0.04),
        (0.55, -0.25, -0.08),
        (0.7, -0.95, -0.08),
        (0.0, -0.85, 0.75),
        (-0.18, -0.95, 0.22),
        (0.18, -0.95, 0.22),
    ]
    faces: list[Face] = [
        (0, 1, 2),
        (0, 2, 3),
        (0, 3, 4),
        (0, 4, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 8),
        (3, 8, 4),
        (4, 8, 5),
        (4, 5, 1),
        (5, 9, 6),
        (6, 9, 7),
        (7, 9, 8),
        (8, 9, 5),
        (10, 11, 12),
        (13, 15, 14),
        (16, 17, 18),
    ]
    return Mesh(name, vertices, faces)


def _obj(mesh: Mesh, *, mtl_name: str = "") -> str:
    lines = ["# Friday generated 3D model"]
    if mtl_name:
        lines.append(f"mtllib {mtl_name}")
    lines.append(f"o {mesh.name}")
    lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in mesh.vertices)
    current_material = ""
    for face, material in zip(mesh.faces, _face_materials(mesh)):
        safe_material = _material_name(material)
        if safe_material != current_material:
            lines.append(f"usemtl {safe_material}")
            current_material = safe_material
        a, b, c = face
        lines.append(f"f {a + 1} {b + 1} {c + 1}")
    return "\n".join(lines) + "\n"


def _mtl(mesh: Mesh) -> str:
    lines = ["# Friday generated material library"]
    for name, color in (mesh.materials or {"default": (0.74, 0.78, 0.82, 1.0)}).items():
        r, g, b, a = color
        lines.append(f"newmtl {_material_name(name)}")
        lines.append(f"Kd {r:.6f} {g:.6f} {b:.6f}")
        lines.append(f"Ka {max(r * 0.25, 0.02):.6f} {max(g * 0.25, 0.02):.6f} {max(b * 0.25, 0.02):.6f}")
        lines.append("Ks 0.080000 0.080000 0.080000")
        lines.append("Ns 18.000000")
        lines.append(f"d {a:.6f}")
        lines.append("illum 2")
    return "\n".join(lines) + "\n"


def _stl(mesh: Mesh) -> str:
    lines = [f"solid {mesh.name}"]
    for face in mesh.faces:
        normal = _normal(mesh.vertices[face[0]], mesh.vertices[face[1]], mesh.vertices[face[2]])
        lines.append(f"  facet normal {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}")
        lines.append("    outer loop")
        for index in face:
            x, y, z = mesh.vertices[index]
            lines.append(f"      vertex {x:.6f} {y:.6f} {z:.6f}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {mesh.name}")
    return "\n".join(lines) + "\n"


def _gltf(mesh: Mesh, *, embed: bool) -> dict[str, Any]:
    payload, views, accessors, primitives, materials = _gltf_payload(mesh)
    data: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "Friday procedural 3D model builder"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": mesh.name}],
        "meshes": [{"primitives": primitives}],
        "materials": materials,
        "buffers": [{"byteLength": len(payload)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    if embed:
        data["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(payload).decode("ascii")
    return data


def _glb(mesh: Mesh) -> bytes:
    payload, views, accessors, primitives, materials = _gltf_payload(mesh)
    gltf = {
        "asset": {"version": "2.0", "generator": "Friday procedural 3D model builder"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": mesh.name}],
        "meshes": [{"primitives": primitives}],
        "materials": materials,
        "buffers": [{"byteLength": len(payload)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    json_chunk = _pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = _pad(payload, b"\x00")
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return (
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(bin_chunk), b"BIN\x00")
        + bin_chunk
    )


def _gltf_payload(mesh: Mesh) -> tuple[bytes, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    positions = b"".join(struct.pack("<fff", *vertex) for vertex in mesh.vertices)
    pos_offset = 0
    payload = positions
    mins = [min(vertex[i] for vertex in mesh.vertices) for i in range(3)]
    maxs = [max(vertex[i] for vertex in mesh.vertices) for i in range(3)]
    views = [
        {"buffer": 0, "byteOffset": pos_offset, "byteLength": len(positions), "target": 34962},
    ]
    accessors = [
        {
            "bufferView": 0,
            "componentType": 5126,
            "count": len(mesh.vertices),
            "type": "VEC3",
            "min": [round(value, 6) for value in mins],
            "max": [round(value, 6) for value in maxs],
        },
    ]
    material_names = list(mesh.materials or {"default": (0.74, 0.78, 0.82, 1.0)})
    grouped: dict[str, list[Face]] = {name: [] for name in material_names}
    for face, material in zip(mesh.faces, _face_materials(mesh)):
        grouped.setdefault(material, []).append(face)
        if material not in material_names:
            material_names.append(material)
    primitives: list[dict[str, Any]] = []
    for material_index, material in enumerate(material_names):
        faces = grouped.get(material) or []
        if not faces:
            continue
        index_bytes = b"".join(struct.pack("<III", *face) for face in faces)
        idx_offset = len(payload)
        payload += index_bytes
        view_index = len(views)
        accessor_index = len(accessors)
        views.append({"buffer": 0, "byteOffset": idx_offset, "byteLength": len(index_bytes), "target": 34963})
        accessors.append({"bufferView": view_index, "componentType": 5125, "count": len(faces) * 3, "type": "SCALAR"})
        primitives.append({"attributes": {"POSITION": 0}, "indices": accessor_index, "mode": 4, "material": material_index})
    materials = [_gltf_material(name, (mesh.materials or {}).get(name, (0.74, 0.78, 0.82, 1.0))) for name in material_names]
    return payload, views, accessors, primitives, materials


def _gltf_material(name: str, color: tuple[float, float, float, float]) -> dict[str, Any]:
    return {
        "name": _material_name(name),
        "pbrMetallicRoughness": {
            "baseColorFactor": [round(float(value), 6) for value in color],
            "metallicFactor": 0.0,
            "roughnessFactor": 0.82,
        },
    }


def _material_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "default")).strip("_.-")
    return cleaned or "default"


def _normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / length, ny / length, nz / length


def _pad(data: bytes, fill: bytes) -> bytes:
    remainder = len(data) % 4
    return data if remainder == 0 else data + fill * (4 - remainder)


def _shape(value: str) -> str:
    lowered = str(value or "").lower()
    if re.search(r"\b(?:city|cities|urban|downtown|town|street\s+block|skyline|skyscrapers?)\b", lowered):
        return "city"
    if re.search(r"\b(?:house|home|cottage|villa|bungalow|mansion|residential)\b", lowered):
        return "house"
    if re.search(r"\b(?:human|person|people|man|woman|character|humanoid|avatar)\b", lowered):
        return "human"
    if re.search(r"\b(?:spaceship|space\s+ship|rocket|starfighter)\b", lowered):
        return "spaceship"
    if re.search(r"\b(?:sphere|planet|ball|globe)\b", lowered):
        return "sphere"
    if re.search(r"\b(?:cylinder|tube|can|pillar|column|tower)\b", lowered):
        return "cylinder"
    if re.search(r"\b(?:cone|pyramid|spire)\b", lowered):
        return "cone"
    if re.search(r"\b(?:terrain|landscape|island|mountain|map)\b", lowered):
        return "terrain"
    return "cube"


def _formats(formats: list[str] | tuple[str, ...] | str | None) -> set[str]:
    raw = formats if formats is not None else str(config_value("model_3d_default_formats", "obj,stl,gltf,glb"))
    if isinstance(raw, str):
        items = [item.strip() for item in re.split(r"[, ]+", raw) if item.strip()]
    else:
        items = [str(item).strip() for item in raw if str(item).strip()]
    allowed = {"obj", "stl", "gltf", "glb"}
    wanted = {item.lower().lstrip(".") for item in items}
    return wanted & allowed or {"obj", "stl", "gltf", "glb"}


def _quality(value: str) -> str:
    raw = str(value or config_value("model_3d_quality_default", "procedural") or "procedural").lower()
    if re.search(r"\b(?:photo\s*real|photorealistic|realistic|studio|blender|zbrush|sculpt|production|cinematic|pbr|high[-\s]?quality)\b", raw):
        return "studio"
    default = str(config_value("model_3d_quality_default", "procedural") or "procedural").lower()
    if default in {"studio", "photorealistic", "blender", "zbrush"}:
        return "studio"
    return "procedural"


def _output_dir() -> Path:
    raw = str(config_value("model_3d_output_dir", str(DATA_DIR / "3d_models")) or "").strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").lower()).strip(".-")
    return cleaned[:48] or "model"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,.!?:;")


def _now_slug() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")


def _summary(manifest: dict[str, Any]) -> str:
    paths = manifest.get("paths") or {}
    exports = " ".join(f"{fmt.upper()}: {path}" for fmt, path in paths.items())
    material_count = len(manifest.get("materials") or [])
    material_note = f" using {material_count} material(s)" if material_count else ""
    return (
        f"3D model created as {manifest['shape']} with {manifest['vertices']} vertices and {manifest['faces']} faces{material_note}. "
        f"{exports}"
    ).strip()
