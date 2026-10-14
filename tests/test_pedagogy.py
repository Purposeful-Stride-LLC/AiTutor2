"""Lesson → practice → check → review, grounded in the learner's sources."""

import io

from aitutor import paths
from aitutor.__main__ import main
from aitutor.grounding import chunk
from aitutor.pedagogy import PHASES, LearnSession
from material import SHELL_TEXT


def _built_course(tmp_path, monkeypatch, capsys):
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    (shelf / "voice.md").write_text(SHELL_TEXT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["build", "--source", str(shelf), "--host", "ollama", "--import"]) == 0
    capsys.readouterr()
    return shelf


def test_chunk_keeps_paragraphs_and_bounds_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(30))
    parts = chunk(text, size=800)
    assert len(parts) > 3 and all(len(p) <= 950 for p in parts)


def test_session_cycle_and_grounding(tmp_path, monkeypatch, capsys, fake_ollama):
    _built_course(tmp_path, monkeypatch, capsys)
    monkeypatch.chdir(tmp_path.parent)  # sources must resolve via the remembered root
    s = LearnSession.start("fake-course")
    assert all(st.found for st in s.grounding.status)
    s.ask()
    sys_prompt = fake_ollama.chats()[-1]["messages"][0]["content"]
    assert "Phase: LESSON" in sys_prompt and "[S1]" in sys_prompt and "pipe" in sys_prompt.lower()
    seen = [s.phase]
    for _ in range(3):
        s.advance()
        seen.append(s.phase)
    assert tuple(seen) == PHASES
    s.set_phase("practice")
    s.ask()  # the task
    task = s.history[-1]["content"]
    s.submit_practice("My practice answer")
    assert s.phase == "check" and s.last_score == 8
    sent = fake_ollama.chats()[-1]["messages"]
    # The grader sees the task it set, then the submission.
    assert sent[-2] == {"role": "assistant", "content": task}
    assert sent[-1] == {"role": "user", "content": "My practice answer"}
    assert "AGAINST THAT TASK" in sent[0]["content"]
    s.set_phase("review")
    assert s.advance().startswith("Unit →") and s.unit_index == 1


def test_missing_sources_are_reported(tmp_path, monkeypatch, capsys, fake_ollama):
    shelf = _built_course(tmp_path, monkeypatch, capsys)
    (shelf / "voice.md").unlink()
    s = LearnSession.start("fake-course")
    assert "not on this computer" in s.opening()


def test_learn_command_runs_full_cycle(tmp_path, monkeypatch, capsys, fake_ollama):
    _built_course(tmp_path, monkeypatch, capsys)
    script = "What is a pipe?\n/next\nI piped ls into grep.\n/next\n/next\n/quit\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(script))
    assert main(["learn", "fake-course"]) == 0
    out = capsys.readouterr()
    assert "SCORE: 8/10" in out.out
    assert "score recorded: 8/10" in out.err
    assert "Phase → practice" in out.out and "Phase → review" in out.out
    assert "Unit → 2. Practice" in out.out


def test_learn_without_ollama_is_clean(tmp_path, monkeypatch, capsys, fake_ollama):
    _built_course(tmp_path, monkeypatch, capsys)
    monkeypatch.setenv("AITUTOR_OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr("sys.stdin", io.StringIO("/quit\n"))
    assert main(["learn", "fake-course"]) == 3
    assert "aitutor setup" in capsys.readouterr().err


def test_guided_tui_end_to_end(tmp_path, monkeypatch, capsys, fake_ollama):
    shelf = tmp_path / "Shelf Folder"
    shelf.mkdir()
    (shelf / "a.txt").write_text(SHELL_TEXT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    script = "\n".join([
        "1",                    # Build a new course
        f'"{shelf}"',           # quoted path, like Windows drag-and-drop
        "",                     # use it
        "",                     # subject default
        "1",                    # adult
        "",                     # goal default
        "",                     # start learning now
        "Explain pipes",        # lesson question
        "/next",                # → practice
        "ls | grep txt",        # practice submission → check
        "/quit",                # leave course
        "q",                    # quit app
    ]) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(script))
    assert main(["tui"]) == 0
    out = capsys.readouterr().out
    assert "Ready:" in out and "Usable files: 1" in out
    assert "Saved fake-course" in out and "Teaching with qwen3:8b" in out
    assert "SCORE: 8/10" in out
    assert paths.course_source_root("fake-course")[1] == "course"


def test_bare_command_prints_menu(capsys):
    assert main([]) == 0
    assert "aitutor setup" in capsys.readouterr().out
