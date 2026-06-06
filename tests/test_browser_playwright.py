from __future__ import annotations

import subprocess
import sys

from core import browser_playwright


def test_available_accepts_global_playwright_cli(monkeypatch):
    monkeypatch.setattr(browser_playwright, "_python_available", lambda: {"available": False, "reason": "playwright_not_installed", "detail": "missing"})
    monkeypatch.setattr(
        browser_playwright,
        "_cli_available",
        lambda: {"available": True, "reason": "playwright_cli_installed", "mode": "cli", "version": "Version 1.60.0"},
    )

    result = browser_playwright.available()

    assert result["available"] is True
    assert result["mode"] == "cli"
    assert result["python_detail"] == "missing"


def test_visual_findings_detect_obvious_bad_rendering():
    findings = browser_playwright._visual_findings(
        [
            {
                "viewport": {"width": 1440, "height": 900, "label": "desktop"},
                "visual": {
                    "horizontalOverflow": True,
                    "firstViewportTextLength": 10,
                    "headings": [
                        {"tag": "h1", "text": "Broken hero", "fontSize": 112, "height": 600, "bottom": 940},
                        {"tag": "h2", "text": "Services"},
                        {"tag": "h2", "text": "Services"},
                    ],
                    "interactives": [{"text": "Start", "href": "#"}],
                    "clipped": [{"text": "Overflow"}],
                },
            }
        ]
    )

    joined = " ".join(findings).lower()
    assert "h1 font is too large" in joined
    assert "horizontal overflow" in joined
    assert "dead link" in joined
    assert "repeated heading" in joined


def test_visual_findings_allow_repeated_navigation_labels():
    findings = browser_playwright._visual_findings(
        [
            {
                "viewport": {"width": 1440, "height": 900, "label": "desktop"},
                "visual": {
                    "horizontalOverflow": False,
                    "firstViewportTextLength": 120,
                    "headings": [{"tag": "h1", "text": "Maison Noire Atelier", "fontSize": 56, "height": 72, "bottom": 220}],
                    "interactives": [
                        {"text": "Collections", "href": "/collections", "rect": {"visible": True}},
                        {"text": "Collections", "href": "/collections", "rect": {"visible": True}},
                        {"text": "Concierge Contact", "href": "/contact", "rect": {"visible": True}},
                    ],
                    "clipped": [],
                    "images": [],
                },
            }
        ]
    )

    assert not any("duplicate visible CTA" in item for item in findings)


def test_visual_findings_detect_blank_visible_canvas():
    findings = browser_playwright._visual_findings(
        [
            {
                "viewport": {"width": 1440, "height": 900, "label": "desktop"},
                "visual": {
                    "horizontalOverflow": False,
                    "firstViewportTextLength": 120,
                    "headings": [{"tag": "h1", "text": "OrbitForge", "fontSize": 56, "height": 72, "bottom": 220}],
                    "interactives": [{"text": "Start", "href": "/start", "rect": {"visible": True}}],
                    "clipped": [],
                    "images": [],
                    "canvases": [
                        {
                            "rect": {"visible": True, "width": 640, "height": 360},
                            "signal": {"nonBlankSample": False, "dataUrlLength": 400},
                        }
                    ],
                },
            }
        ]
    )

    assert any("canvas/3D scene appears blank" in item for item in findings)


def test_ensure_available_auto_installs_when_missing(tmp_path, monkeypatch):
    checks = iter(
        [
            {"available": False, "reason": "playwright_not_installed"},
            {"available": True, "reason": "playwright_installed"},
        ]
    )
    commands = []

    monkeypatch.setattr(browser_playwright, "available", lambda: next(checks))
    monkeypatch.setattr(browser_playwright, "config_value", lambda key, default=None: True if key == "browser_playwright_auto_install" else default)

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(browser_playwright.command_runner, "run", fake_run)

    result = browser_playwright.ensure_available(tmp_path)

    assert result["available"] is True
    assert result["install_attempted"] is True
    assert result["browser_channel"] == "chrome"
    assert len(result["install_logs"]) == 1
    assert commands[0][0] == f"{sys.executable} -m pip install playwright"


def test_ensure_available_installs_browser_when_no_channel(tmp_path, monkeypatch):
    checks = iter(
        [
            {"available": False, "reason": "playwright_not_installed"},
            {"available": True, "reason": "playwright_installed"},
            {"available": True, "reason": "playwright_installed"},
        ]
    )
    commands = []

    monkeypatch.setattr(browser_playwright, "available", lambda: next(checks))
    monkeypatch.setattr(
        browser_playwright,
        "config_value",
        lambda key, default=None: "" if key == "browser_playwright_channel" else (True if key == "browser_playwright_auto_install" else default),
    )

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(browser_playwright.command_runner, "run", fake_run)

    result = browser_playwright.ensure_available(tmp_path)

    assert result["available"] is True
    assert result["install_attempted"] is True
    assert len(result["install_logs"]) == 2
    assert commands[1] == f"{sys.executable} -m playwright install chromium"


def test_ensure_available_reports_install_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_playwright, "available", lambda: {"available": False, "reason": "playwright_not_installed"})
    monkeypatch.setattr(browser_playwright, "config_value", lambda key, default=None: True if key == "browser_playwright_auto_install" else default)
    monkeypatch.setattr(
        browser_playwright.command_runner,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "failed\n"),
    )

    result = browser_playwright.ensure_available(tmp_path)

    assert result["available"] is False
    assert result["reason"] == "playwright_install_failed"
    assert result["install_attempted"] is True
    assert result["install_logs"]
