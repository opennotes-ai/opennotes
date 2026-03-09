from src.fact_checking.repository import strip_discord_markdown


class TestStripDiscordMarkdown:
    def test_strips_strikethrough(self):
        assert strip_discord_markdown("~~as they should~~") == "as they should"

    def test_strips_bold(self):
        assert strip_discord_markdown("**important**") == "important"

    def test_strips_underline(self):
        assert strip_discord_markdown("__underlined__") == "underlined"

    def test_strips_spoiler(self):
        assert strip_discord_markdown("||hidden||") == "hidden"

    def test_strips_inline_code(self):
        assert strip_discord_markdown("`code`") == "code"

    def test_strips_code_block(self):
        assert strip_discord_markdown("```python\ncode\n```") == "code\n"

    def test_strips_mixed_markdown(self):
        assert strip_discord_markdown("~~strike~~ and **bold**") == "strike and bold"

    def test_plain_text_unchanged(self):
        assert strip_discord_markdown("just plain text") == "just plain text"

    def test_empty_string(self):
        assert strip_discord_markdown("") == ""

    def test_single_special_chars_preserved(self):
        assert strip_discord_markdown("a ~ b") == "a ~ b"
