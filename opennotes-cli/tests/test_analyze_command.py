from __future__ import annotations

from opennotes_cli.commands.analyze import analyze


class TestAnalyzeCommandGroup:
    def test_analyze_is_click_group(self):
        import click

        assert isinstance(analyze, click.Group)

    def test_mf_subcommand_exists(self):
        assert "mf" in analyze.commands

    def test_mf_command_has_rescore_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "rescore" in param_names

    def test_mf_command_has_format_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "fmt" in param_names

    def test_mf_command_has_sections_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "sections" in param_names

    def test_mf_command_has_no_prompt_option(self):
        mf_cmd = analyze.commands["mf"]
        param_names = [p.name for p in mf_cmd.params]
        assert "no_prompt" in param_names
