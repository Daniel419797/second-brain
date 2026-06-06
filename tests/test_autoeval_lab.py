import json
from pathlib import Path

from api.server import create_app
from core import autoeval_lab, evaluation_lab


def _write_project(root: Path, *, bad: bool = True) -> None:
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "components" / "Landing").mkdir(parents=True)
    (root / "src" / "lib").mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"build": "next build", "test": "vitest"},
                "dependencies": {"next": "latest", "react": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    text = (
        "export default function Page(){return <main><h1>AI-assisted everyday workflow tool</h1><a href=\"#\">Open workspace</a></main>}"
        if bad
        else "export default function Page(){return <main><h1>Build permit approvals with live project evidence</h1><a href=\"/contact\">Request a walkthrough</a></main>}"
    )
    (root / "src" / "app" / "page.tsx").write_text(text, encoding="utf-8")
    (root / "src" / "app" / "globals.css").write_text("body { margin: 0; }\n", encoding="utf-8")
    (root / "src" / "lib" / "siteContent.ts").write_text(
        "export const siteContent = { brand: 'CivicBuild', proof: 'permits inspections contractors' };\n",
        encoding="utf-8",
    )


def test_autoeval_score_writes_program_and_score_report(monkeypatch, tmp_path):
    monkeypatch.setattr(autoeval_lab, "DB_PATH", tmp_path / "autoeval.sqlite3")
    monkeypatch.setattr(evaluation_lab, "DB_PATH", tmp_path / "evaluation.sqlite3")
    _write_project(tmp_path, bad=True)

    program = autoeval_lab.ensure_program(tmp_path, "Improve this construction workflow landing page.")
    score = autoeval_lab.score_project(tmp_path, "Improve this construction workflow landing page.", stack={"stack": "nextjs"})

    assert Path(program["program_path"]).exists()
    assert "AutoResearch-style loop without GPU training" in Path(program["program_path"]).read_text(encoding="utf-8")
    assert score["score"] < 100
    assert (tmp_path / ".friday" / "autoeval" / "latest-score.json").exists()
    assert score["breakdown"]["quality"] <= 100


def test_autoeval_keeps_improving_command(monkeypatch, tmp_path):
    monkeypatch.setattr(autoeval_lab, "DB_PATH", tmp_path / "autoeval.sqlite3")
    monkeypatch.setattr(evaluation_lab, "DB_PATH", tmp_path / "evaluation.sqlite3")
    _write_project(tmp_path, bad=True)
    (tmp_path / "improve.py").write_text(
        "from pathlib import Path\n"
        "p=Path('src/app/page.tsx')\n"
        "p.write_text('export default function Page(){return <main><h1>Permit approvals with live project evidence</h1><a href=\"/contact\">Request a walkthrough</a></main>}', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = autoeval_lab.run_experiment(
        tmp_path,
        "Improve this construction workflow landing page.",
        target_files=["src/app/page.tsx"],
        experiment_command="python improve.py",
        min_delta=1,
        stack={"stack": "nextjs"},
    )

    assert result["status"] == "kept"
    assert result["kept"] is True
    assert result["improvement"] > 0
    assert "AI-assisted everyday workflow tool" not in (tmp_path / "src" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert (tmp_path / ".friday" / "autoeval" / "score-history.json").exists()
    assert any("run.json" in item for item in result["artifacts"])
    assert autoeval_lab.history(root=tmp_path)[0]["status"] == "kept"


def test_autoeval_reverts_regressing_command(monkeypatch, tmp_path):
    monkeypatch.setattr(autoeval_lab, "DB_PATH", tmp_path / "autoeval.sqlite3")
    monkeypatch.setattr(evaluation_lab, "DB_PATH", tmp_path / "evaluation.sqlite3")
    _write_project(tmp_path, bad=False)
    original = (tmp_path / "src" / "app" / "page.tsx").read_text(encoding="utf-8")
    (tmp_path / "worsen.py").write_text(
        "from pathlib import Path\n"
        "Path('src/app/page.tsx').write_text('export default function Page(){return <main><h1>AI-assisted everyday workflow tool</h1><a href=\"#\">Open workspace</a></main>}', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = autoeval_lab.run_experiment(
        tmp_path,
        "Improve this construction workflow landing page.",
        target_files=["src/app/page.tsx"],
        experiment_command="python worsen.py",
        min_delta=1,
        stack={"stack": "nextjs"},
    )

    assert result["status"] == "reverted"
    assert result["reverted"] is True
    assert (tmp_path / "src" / "app" / "page.tsx").read_text(encoding="utf-8") == original


def test_autoeval_routes_are_registered():
    routes = {getattr(route, "path", "") for route in create_app().routes}
    assert "/autoeval/status" in routes
    assert "/autoeval/program" in routes
    assert "/autoeval/score" in routes
    assert "/autoeval/run" in routes
    assert "/autoeval/history" in routes
