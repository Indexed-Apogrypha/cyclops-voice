from cyclops_voice.chunker import chunk_text


def test_splits_on_sentences():
    out = chunk_text("Hello there. All systems online! Status?")
    assert out == ["Hello there.", "All systems online!", "Status?"]


def test_blank_input():
    assert chunk_text("   \n  ") == []


def test_long_sentence_is_split_by_length():
    long = "word " * 100  # 500 chars, no sentence punctuation
    out = chunk_text(long, max_chars=240)
    assert len(out) >= 2
    assert all(len(c) <= 240 for c in out)
    assert "".join(out).replace(" ", "") == long.replace(" ", "")


def test_newlines_break_chunks():
    out = chunk_text("Line one\nLine two")
    assert out == ["Line one", "Line two"]


def test_single_long_word_is_split():
    long_word = "x" * 500
    out = chunk_text(long_word, max_chars=240)
    assert len(out) >= 2
    assert all(len(c) <= 240 for c in out)
    assert "".join(out) == long_word
