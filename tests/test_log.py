"""Tests for marrow_core.log — setup_logging with optional file sink."""

from __future__ import annotations

from loguru import logger

from marrow_core.log import setup_logging


def test_setup_logging_stderr_only(capsys):
    """setup_logging without log_file should not create any files."""
    setup_logging(verbose=False, json_logs=False)
    logger.info("stderr-only message")
    # Nothing should be written to a file — just confirm no exceptions.


def test_setup_logging_creates_log_file(tmp_path):
    """When log_file is given, the file should be created and written to."""
    log_file = tmp_path / "marrow.log"
    setup_logging(verbose=False, json_logs=False, log_file=log_file)
    logger.info("hello from file sink")
    # Allow loguru's enqueue thread to flush.
    logger.complete()
    assert log_file.exists(), "log file was not created"
    content = log_file.read_text()
    assert "hello from file sink" in content


def test_setup_logging_json_file(tmp_path):
    """JSON mode should write serialized JSON to the file sink."""
    log_file = tmp_path / "marrow.log"
    setup_logging(verbose=False, json_logs=True, log_file=log_file)
    logger.info("json-sink test")
    logger.complete()
    content = log_file.read_text()
    # Each line should be valid JSON with a "text" key from loguru serialization.
    import json

    for line in content.splitlines():
        if line.strip():
            record = json.loads(line)
            assert "text" in record or "message" in record or "record" in record


def test_setup_logging_creates_parent_dirs(tmp_path):
    """log_file parent directories should be created automatically."""
    log_file = tmp_path / "nested" / "deep" / "marrow.log"
    setup_logging(log_file=log_file)
    logger.info("nested dirs test")
    logger.complete()
    assert log_file.exists()


def test_setup_logging_verbose(tmp_path):
    """verbose=True should lower the level to DEBUG."""
    log_file = tmp_path / "debug.log"
    setup_logging(verbose=True, json_logs=False, log_file=log_file)
    logger.debug("debug message here")
    logger.complete()
    content = log_file.read_text()
    assert "debug message here" in content


def test_setup_logging_no_file_no_exception():
    """Calling setup_logging without log_file must not raise."""
    setup_logging()  # all defaults — should be a no-op on file side


def test_setup_logging_idempotent(tmp_path):
    """Calling setup_logging twice should not raise (loguru.remove resets sinks)."""
    log_file = tmp_path / "marrow.log"
    setup_logging(log_file=log_file)
    setup_logging(log_file=log_file)
    logger.info("after re-setup")
    logger.complete()
    content = log_file.read_text()
    # Should contain the message at least once.
    assert "after re-setup" in content
