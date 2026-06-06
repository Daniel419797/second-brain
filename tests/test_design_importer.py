import json

from core import design_importer


def test_external_html_import_preserves_static_document_route(tmp_path):
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script src="https://cdn.tailwindcss.com"></script>
  <script id="tailwind-config">
    tailwind.config = { theme: { extend: { colors: { ink: "#111111" } } } };
  </script>
  <title>Vale & Vellum</title>
</head>
<body>
  <main class="min-h-screen bg-stone-50 text-ink">
    <section class="relative min-h-screen flex items-center justify-center">
      <h1 class="text-8xl">A quieter standard of luxury, made visible.</h1>
      <a href="#inquiry">Request concierge access</a>
    </section>
  </main>
</body>
</html>"""

    result = design_importer.import_and_implement(
        request="Build a landing page for Vale & Vellum from this exact design.",
        product_name="Vale & Vellum",
        source_type="stitch_output",
        source=html,
        root=tmp_path / "vale-vellum",
        verify=False,
    )
    project_root = tmp_path / "vale-vellum"

    assert result["ok"] is True
    assert result["status"] == "implemented"
    assert (project_root / ".friday" / "design-import" / "source-manifest.json").exists()
    assert (project_root / ".friday" / "design" / "frontend-handoff.json").exists()
    assert (project_root / "public" / "friday-stitch" / "home.html").exists()
    route = (project_root / "src" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "StitchPageSurface" in route
    assert "redirect(" not in route
    assert "next/navigation" not in route

    handoff = json.loads((project_root / ".friday" / "design" / "frontend-handoff.json").read_text(encoding="utf-8"))
    assert handoff["source"] == "external_design_import"
    assert handoff["pages"][0]["source_type"] == "stitch_output"
    assert handoff["pages"][0]["fidelity"] == "exact_html"


def test_external_html_import_copies_root_relative_assets(tmp_path):
    source_project = tmp_path / "source-project"
    source_public = source_project / "public"
    source_html = source_public / "friday-stitch" / "home.html"
    source_asset = source_public / "friday-assets" / "hero.png"
    source_asset.parent.mkdir(parents=True)
    source_html.parent.mkdir(parents=True)
    source_asset.write_bytes(b"fake-png")
    source_html.write_text(
        "<!doctype html><html><body><main><img src='/friday-assets/hero.png' alt='Hero'/><h1>Vale & Vellum</h1></main></body></html>",
        encoding="utf-8",
    )

    result = design_importer.import_and_implement(
        request="Build the supplied website design.",
        product_name="Vale & Vellum",
        source_type="stitch_output",
        source_path=str(source_html),
        root=tmp_path / "imported-site",
        verify=False,
    )

    copied_asset = tmp_path / "imported-site" / "public" / "friday-assets" / "hero.png"
    assert result["ok"] is True
    assert copied_asset.exists()
    assert str(copied_asset) in result["pages"][0]["source_artifacts"]


def test_external_html_import_normalizes_links_and_accessible_names(tmp_path):
    html = """<!doctype html><html><body>
<nav><a href="/process">Process</a><a href="/services">Services</a><a href="/contact">Inquiry</a></nav>
<main>
  <section><h1>Vale & Vellum</h1><button><span>shopping_bag</span></button></section>
  <section><h2>The Journey</h2><p>Studio process proof.</p></section>
  <section><h2>Secure Your Date</h2><input type="email" placeholder="Email Address"/><a href="#">Studio Location</a></section>
</main>
</body></html>"""

    result = design_importer.import_and_implement(
        request="Build the supplied Vale & Vellum website.",
        product_name="Vale & Vellum",
        source_type="stitch_output",
        source=html,
        root=tmp_path / "normalized-site",
        verify=False,
    )
    static_html = (tmp_path / "normalized-site" / ".friday" / "design" / "selected-design.html").read_text(encoding="utf-8")

    assert result["ok"] is True
    assert 'href="#process"' in static_html
    assert 'href="#inquiry"' in static_html
    assert 'href="/services"' not in static_html
    assert 'href="/contact"' not in static_html
    assert 'id="process"' in static_html
    assert 'id="inquiry"' in static_html
    assert 'aria-label="Shopping bag"' in static_html
    assert 'aria-label="Email Address"' in static_html


def test_design_brief_import_is_marked_as_reference_reconstruction(tmp_path):
    result = design_importer.import_and_implement(
        request="Build a calm editorial website for a private interior studio.",
        product_name="Stillroom Studio",
        source_type="design_brief",
        source="A quiet, image-led editorial website with services, process, proof, and a private inquiry form.",
        root=tmp_path / "stillroom-studio",
        verify=False,
    )
    project_root = tmp_path / "stillroom-studio"

    assert result["ok"] is True
    assert result["pages"][0]["fidelity"] == "reference_reconstruction"
    assert any("reconstructed" in gap.lower() for gap in result["gaps"])
    assert (project_root / ".friday" / "design-import" / "sources" / "home" / "source.md").exists()
    assert (project_root / ".friday" / "design" / "frontend-handoff.json").exists()
    assert (project_root / "src" / "app" / "page.tsx").exists()
    content = (project_root / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    assert "Stillroom Studio" in content


def test_v0_react_output_is_preserved_as_component_route(tmp_path):
    source = """
export default function Landing() {
  return (
    <main className="min-h-screen bg-black text-white">
      <section>
        <h1>Nocturne Audio</h1>
        <p>Studio-grade listening rooms for private collectors.</p>
      </section>
    </main>
  );
}
"""

    result = design_importer.import_and_implement(
        request="Implement this v0 output as a Next.js landing page.",
        product_name="Nocturne Audio",
        source_type="v0_output",
        source=source,
        root=tmp_path / "nocturne-audio",
        verify=False,
    )
    project_root = tmp_path / "nocturne-audio"

    assert result["ok"] is True
    assert result["pages"][0]["fidelity"] == "source_code_preserved"
    component = project_root / "src" / "components" / "ExternalDesign" / "HomeImportedDesign.tsx"
    route = project_root / "src" / "app" / "page.tsx"
    assert component.exists()
    assert route.exists()
    assert "Nocturne Audio" in component.read_text(encoding="utf-8")
    assert "ExternalDesign/HomeImportedDesign" in route.read_text(encoding="utf-8")
