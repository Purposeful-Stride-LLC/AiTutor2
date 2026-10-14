"""Stress-test fixes, full-screen TUI: 80x24 Build button, typed input kept while busy,
Escape goes Home, no re-run at unit 1, Build anyway, odd replies and worker errors."""

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Input, OptionList, Static  # noqa: E402

from aitutor.tui.full import AiTutorApp, BuildScreen, HomeScreen, LearnScreen, PickScreen  # noqa: E402
from material import SHELL_TEXT  # noqa: E402


async def _until(pilot, cond, timeout=15.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("timed out waiting for the UI")
        await pilot.pause(0.05)


async def _click_until(pilot, selector, cond, tries=5):
    """Click once the layout has settled; the report text above the button grows when the
    check finishes, so a click on the same frame can land where the button used to be."""
    for _ in range(tries):
        await pilot.pause(0.2)
        await pilot.click(selector)
        try:
            await _until(pilot, cond, timeout=3.0)
            return
        except AssertionError:
            continue
    raise AssertionError(f"clicking {selector} never took effect")


def _shelf(tmp_path, text=SHELL_TEXT):
    shelf = tmp_path / "shelf"
    shelf.mkdir(exist_ok=True)
    (shelf / "shell.md").write_text(text, encoding="utf-8")
    return shelf


async def _to_pick(app, pilot, shelf, subject=None):
    await _until(pilot, lambda: app.report is not None and app.report.ready)
    await _click_until(pilot, "#continue", lambda: isinstance(app.screen, HomeScreen))
    await pilot.pause(0.1)
    app.screen.query_one(OptionList).highlighted = 0
    await pilot.press("enter")
    await _until(pilot, lambda: isinstance(app.screen, PickScreen))
    box = app.screen.query_one("#path", Input)
    box.value = str(shelf)
    box.focus()
    await pilot.press("enter")
    await _until(pilot, lambda: not app.screen.query_one("#build", Button).disabled)
    if subject is not None:
        app.screen.query_one("#subject", Input).value = subject


async def _to_learn(app, pilot, shelf):
    await _to_pick(app, pilot, shelf)
    await pilot.click("#build")
    await _until(pilot, lambda: isinstance(app.screen, BuildScreen))
    await _until(pilot, lambda: not app.screen.query_one("#learn", Button).disabled)
    await pilot.click("#learn")
    await _until(pilot, lambda: isinstance(app.screen, LearnScreen))
    learn = app.screen
    await _until(pilot, lambda: learn.session is not None and not learn.busy and learn.session.history)
    return learn


def _log(app):
    w = app.screen.query_one("#buildlog", Static)
    return str(getattr(w, "content", None) or w.render())


def test_build_button_visible_and_clickable_at_80x24(tmp_path, fake_ollama):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await _to_pick(app, pilot, _shelf(tmp_path))
            btn = app.screen.query_one("#build", Button)
            r = btn.region
            assert r.height > 0 and r.y + r.height <= 24 and r.x + r.width <= 80, r
            await pilot.click("#build")
            await _until(pilot, lambda: isinstance(app.screen, BuildScreen))
    asyncio.run(go())


def test_typed_text_kept_while_model_busy(tmp_path, fake_ollama):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            learn = await _to_learn(app, pilot, _shelf(tmp_path))
            fake_ollama.delay = 0.6
            n = len(fake_ollama.chats())
            msg = learn.query_one("#msg", Input)
            msg.focus()
            msg.value = "first question"
            await pilot.press("enter")
            await _until(pilot, lambda: learn.busy)
            msg.value = "typed while busy"
            await pilot.press("enter")
            await pilot.pause(0.1)
            assert msg.value == "typed while busy"  # not thrown away
            fake_ollama.delay = 0.0
            await _until(pilot, lambda: not learn.busy)
            await pilot.press("enter")  # now it goes
            await _until(pilot, lambda: len(fake_ollama.chats()) >= n + 2 and not learn.busy)
            assert fake_ollama.chats()[-1]["messages"][-1]["content"] == "typed while busy"
            assert msg.value == ""
    asyncio.run(go())


def test_escape_on_learn_goes_home_and_ctrl_p_at_unit_1_does_nothing(tmp_path, fake_ollama):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            learn = await _to_learn(app, pilot, _shelf(tmp_path))
            n = len(fake_ollama.chats())
            await pilot.press("ctrl+p")
            await pilot.pause(0.3)
            assert len(fake_ollama.chats()) == n and learn.session.unit_index == 0
            await pilot.press("escape")
            await _until(pilot, lambda: isinstance(app.screen, HomeScreen))
            assert not any(isinstance(s, (PickScreen, BuildScreen, LearnScreen)) for s in app.screen_stack)
    asyncio.run(go())


def test_build_anyway_button_for_weak_material(tmp_path, fake_ollama):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            await _to_pick(app, pilot, _shelf(tmp_path), subject="HVAC refrigerant certification")
            await pilot.click("#build")
            await _until(pilot, lambda: isinstance(app.screen, BuildScreen))
            anyway = app.screen.query_one("#anyway", Button)
            await _until(pilot, lambda: anyway.display)
            assert "none of the words" in _log(app) and not fake_ollama.chats()
            await pilot.click("#anyway")
            await _until(pilot, lambda: not app.screen.query_one("#learn", Button).disabled)
            assert "built anyway although" in _log(app)
    asyncio.run(go())


def test_default_subject_is_not_checked(tmp_path, fake_ollama):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            await _to_pick(app, pilot, _shelf(tmp_path))  # subject = "Shelf" (folder name)
            await pilot.click("#build")
            await _until(pilot, lambda: isinstance(app.screen, BuildScreen))
            await _until(pilot, lambda: not app.screen.query_one("#learn", Button).disabled)
    asyncio.run(go())


@pytest.mark.parametrize("reply", ["[1, 2, 3]", "Sorry, I cannot build a course."])
def test_odd_build_reply_shows_error_and_app_lives(tmp_path, fake_ollama, reply):
    async def go():
        fake_ollama.build_reply = reply
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            await _to_pick(app, pilot, _shelf(tmp_path))
            await pilot.click("#build")
            await _until(pilot, lambda: isinstance(app.screen, BuildScreen) and "Build failed" in _log(app))
            assert app.is_running and app.screen.query_one("#learn", Button).disabled
            await pilot.click("#back")
            await _until(pilot, lambda: isinstance(app.screen, PickScreen))
    asyncio.run(go())


def test_learn_worker_error_is_shown_not_fatal(tmp_path, fake_ollama, monkeypatch):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            learn = await _to_learn(app, pilot, _shelf(tmp_path))

            def boom(*a, **k):
                raise RuntimeError("unexpected reply shape")
            monkeypatch.setattr(learn.session, "ask", boom)
            msg = learn.query_one("#msg", Input)
            msg.focus()
            msg.value = "hello"
            await pilot.press("enter")
            await pilot.pause(0.5)
            await _until(pilot, lambda: not learn.busy)
            assert app.is_running
            texts = [getattr(m, "source", "") or getattr(m, "_markdown", "") for m in learn.query("Markdown")]
            assert any("Something went wrong" in t and "unexpected reply shape" in t for t in texts)
    asyncio.run(go())


def test_scanned_pdf_folder_explained_in_tui(tmp_path, fake_ollama):
    pypdf = pytest.importorskip("pypdf")
    shelf = tmp_path / "scans"
    shelf.mkdir()
    w = pypdf.PdfWriter()
    w.add_blank_page(width=612, height=792)
    with open(shelf / "scan.pdf", "wb") as f:
        w.write(f)

    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            await _to_pick(app, pilot, shelf)
            await pilot.click("#build")
            await _until(pilot, lambda: isinstance(app.screen, BuildScreen) and "Cannot build" in _log(app))
            assert "scanned" in _log(app) and "OCR" in _log(app)
    asyncio.run(go())


def test_ctrl_p_goes_back_a_unit_even_from_the_text_box(tmp_path, fake_ollama):
    async def go():
        app = AiTutorApp(start_dir=tmp_path)
        async with app.run_test(size=(140, 44)) as pilot:
            learn = await _to_learn(app, pilot, _shelf(tmp_path))
            learn.session.set_unit(1)
            learn.query_one("#msg", Input).focus()
            n = len(fake_ollama.chats())
            await pilot.press("ctrl+p")
            await _until(pilot, lambda: learn.session.unit_index == 0 and len(fake_ollama.chats()) > n and not learn.busy)
            assert not any(type(s).__name__ == "CommandPalette" for s in app.screen_stack)
    asyncio.run(go())
