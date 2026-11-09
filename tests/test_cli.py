from __future__ import annotations

import json

import pytest

import job_finder.core as core
from job_finder import cli
from job_finder.config import load_config
from job_finder.models import Job
from job_finder.notify import send_ntfy
from job_finder.sources import REGISTRY, SourceSkipped
from job_finder.sources.base import SourceSpec


@pytest.fixture
def fake_sources(monkeypatch):
    """Replace the registry with three controllable sources."""

    def good(client, cfg):
        return [
            Job("Junior Python Developer", "https://ok/1", "good", company="Acme"),
            Job("Senior Python Developer", "https://ok/2", "good", company="Globex"),
        ]

    def broken(client, cfg):
        raise RuntimeError("boom")

    def keyed(client, cfg):
        raise SourceSkipped("needs a key")

    registry = {
        "good": SourceSpec("good", good, "remote", "", True),
        "broken": SourceSpec("broken", broken, "remote", "", True),
        "keyed": SourceSpec("keyed", keyed, "remote", "", False),
    }
    monkeypatch.setattr(core, "REGISTRY", registry)
    monkeypatch.setattr(cli, "REGISTRY", registry)
    return registry


@pytest.fixture
def cfgfile(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[general]\noutput_dir = "{tmp_path / "out"}"\nhistory_db = "{tmp_path / "h.db"}"\n'
        '[search]\nprofile = "python"\n',
        encoding="utf-8",
    )
    return str(path)


def test_one_broken_source_does_not_kill_the_run(fake_sources, cfgfile, capsys):
    code = cli.main(["--config", cfgfile, "--sources", "good,broken,keyed", "--no-emoji"])
    out, err = capsys.readouterr()
    assert code == 0
    assert "Junior Python Developer" in out
    assert "broken failed" in err and "keyed skipped" in err


def test_all_sources_failing_exits_nonzero(fake_sources, cfgfile, capsys):
    assert cli.main(["--config", cfgfile, "--sources", "broken"]) == 1
    assert "No source returned data" in capsys.readouterr().err


def test_new_then_seen_across_runs_and_mark_applied(fake_sources, cfgfile, capsys):
    cli.main(["--config", cfgfile, "--sources", "good", "--format", "json"])
    first = json.loads(capsys.readouterr().out)
    assert all(j["is_new"] for j in first["jobs"])

    cli.main(["--config", cfgfile, "--sources", "good", "--format", "json"])
    second = json.loads(capsys.readouterr().out)
    assert not any(j["is_new"] for j in second["jobs"])

    job_id = second["jobs"][0]["id"]
    assert cli.main(["--config", cfgfile, "mark", job_id, "ignored"]) == 0
    capsys.readouterr()  # discard the "Marked ..." confirmation
    cli.main(["--config", cfgfile, "--sources", "good", "--format", "json"])
    third = json.loads(capsys.readouterr().out)
    assert job_id not in {j["id"] for j in third["jobs"]}  # ignored jobs are hidden


def test_new_only_flag(fake_sources, cfgfile, capsys):
    args = ["--config", cfgfile, "--sources", "good", "--new-only", "-f", "json"]
    cli.main(args)
    assert len(json.loads(capsys.readouterr().out)["jobs"]) == 2
    cli.main(args)
    assert json.loads(capsys.readouterr().out)["jobs"] == []


def test_output_file_bare_name_goes_to_output_dir_with_format_from_extension(
    fake_sources, cfgfile, tmp_path, capsys
):
    cli.main(["--config", cfgfile, "--sources", "good", "-o", "report.html"])
    target = tmp_path / "out" / "report.html"
    assert "Saved" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_output_file_is_utf8_even_with_emoji(fake_sources, cfgfile, tmp_path):
    cli.main(["--config", cfgfile, "--sources", "good", "-o", "r.md"])
    text = (tmp_path / "out" / "r.md").read_text(encoding="utf-8")
    assert "🆕" in text


def test_search_term_filters(fake_sources, cfgfile, capsys):
    cli.main(
        ["--config", cfgfile, "--sources", "good", "-s", "globex", "-f", "json", "--no-history"]
    )
    jobs = json.loads(capsys.readouterr().out)["jobs"]
    assert [j["company"] for j in jobs] == ["Globex"]


def test_bad_inputs_return_exit_code_2(fake_sources, cfgfile, capsys):
    assert cli.main(["--config", cfgfile, "--sources", "nope"]) == 2
    assert cli.main(["--config", cfgfile, "--since", "soon"]) == 2
    assert cli.main(["--config", cfgfile, "-p", "nope"]) == 2
    assert cli.main(["--config", "/does/not/exist.toml"]) == 2
    assert "error:" in capsys.readouterr().err


def test_sources_command_lists_everything(fake_sources, cfgfile, capsys):
    assert cli.main(["--config", cfgfile, "sources"]) == 0
    out = capsys.readouterr().out
    assert "good" in out and "opt-in" in out


def test_demo_runs_offline_without_touching_history(cfgfile, capsys, tmp_path):
    assert "demo" in REGISTRY
    assert cli.main(["--config", cfgfile, "--demo", "-p", "python", "--no-emoji"]) == 0
    assert "Junior Python Automation Developer" in capsys.readouterr().out
    assert not (tmp_path / "h.db").exists()


def test_init_config_writes_loadable_example(tmp_path, capsys):
    path = tmp_path / "cfg" / "config.toml"
    assert cli.main(["--config", str(path), "init-config"]) == 0
    assert cli.main(["--config", str(path), "init-config"]) == 1  # refuses to overwrite
    cfg = load_config(path)
    assert cfg.profile == "python"
    assert "freelance-python" in cfg.custom_profiles


def test_ntfy_topic_validation_and_payload(monkeypatch):
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, data, headers, timeout):
        sent.update(url=url, data=data, headers=headers)
        return Resp()

    monkeypatch.setattr("job_finder.notify.requests.post", fake_post)
    job = Job("Python Dev", "https://x/1", "t", company="Acme", score=5)
    send_ntfy("my-topic", [job])
    assert sent["url"] == "https://ntfy.sh/my-topic"
    assert b"Python Dev - Acme" in sent["data"]
    with pytest.raises(ValueError, match="topic"):
        send_ntfy("../../evil", [job])
    sent.clear()
    send_ntfy("my-topic", [])  # nothing new -> no request
    assert not sent
