from src.research_agent.public_updates import PublicUpdateStreamParser


def test_emits_only_tagged_public_text_across_chunk_boundaries() -> None:
    parser = PublicUpdateStreamParser()
    visible: list[str] = []

    for chunk in ["hidden<public_", "update>先查行情", "。</public_update>{\"summary\":"]:
        visible.extend(parser.feed(chunk))
    visible.extend(parser.finish())

    assert "".join(visible) == "先查行情。"


def test_supports_multiple_public_segments_without_leaking_other_content() -> None:
    parser = PublicUpdateStreamParser()

    visible = parser.feed(
        "<public_update>第一段</public_update>noise"
        "<public_update>第二段</public_update>"
    )

    assert "".join(visible) == "第一段第二段"


def test_discards_unterminated_private_content_but_flushes_public_content() -> None:
    private = PublicUpdateStreamParser()
    public = PublicUpdateStreamParser()

    assert private.feed("final-json") == []
    assert private.finish() == []
    assert public.feed("<public_update>正在核验</public_") == ["正在核验"]
    assert public.finish() == []
