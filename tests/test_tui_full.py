"""Full-screen Textual UI, driven headlessly against the fake Ollama."""

import asyncio
import os
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Input, OptionList  # noqa: E402

from aitutor.tui.full import AiTutorApp, BuildScreen, HomeScreen, LearnScreen, PickScreen  # noqa: E402
from material import SHELL_TEXT  # noqa: E402


async def _until(pilot, cond, timeout=15.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("timed out waiting for the UI")
        await pilot.pause(0.05)


def _shot(app, name):
    out = os.environ.get("AITUTOR_SCREENSHOTS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        app.save_screenshot(filename=f"{name}.svg", path=out)


def test_full_tui_flow(tmp_path, fake_ollama):
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    (shelf / "voice.md").write_text(SHELL_TEXT, encoding="utf-8")

    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            await _until(pilot, lambda: app.report is not None)
            await pilot.pause(0.1)
            assert app.report.ready
            assert not app.screen.query_one("#continue", Button).disabled
            _shot(app, "1_requirements")
            await pilot.click("#continue")
            await _until(pilot, lambda: isinstance(app.screen, HomeScreen))
            await pilot.pause(0.1)
            _shot(app, "2_home")
            ol = app.screen.query_one(OptionList)
            ol.highlighted = 0
            await pilot.press("enter")
            await _until(pilot, lambda: isinstance(app.screen, PickScreen))
            box = app.screen.query_one("#path", Input)
            box.value = str(shelf)
            box.focus()
            await pilot.press("enter")
            await _until(pilot, lambda: not app.screen.query_one("#build", Button).disabled)
            await pilot.pause(0.2)
            _shot(app, "3_pick_source")
            await pilot.click("#build")
            await _until(pilot, lambda: isinstance(app.screen, BuildScreen))
            await _until(pilot, lambda: not app.screen.query_one("#learn", Button).disabled)
            assert app.screen.course_id == "fake-course"
            _shot(app, "4_built")
            await pilot.click("#learn")
            await _until(pilot, lambda: isinstance(app.screen, LearnScreen))
            learn = app.screen
            await _until(pilot, lambda: learn.session is not None and not learn.busy and learn.session.history)
            await pilot.press("ctrl+n")  # → practice
            await _until(pilot, lambda: learn.session.phase == "practice" and not learn.busy)
            await pilot.pause(0.1)
            msg = learn.query_one("#msg", Input)
            msg.focus()
            msg.value = "The team approved the budget."
            await pilot.press("enter")
            await _until(pilot, lambda: learn.session.last_score == 8 and not learn.busy)
            await pilot.pause(0.3)
            _shot(app, "5_learn_check")
            assert learn.session.phase == "check"

    asyncio.run(go())


def test_full_tui_not_ready_disables_continue(tmp_path):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await _until(pilot, lambda: app.report is not None)
            await pilot.pause(0.1)
            assert not app.report.ready
            assert app.screen.query_one("#continue", Button).disabled
            _shot(app, "0_not_ready")

    asyncio.run(go())
