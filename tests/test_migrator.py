"""Tests for main/utils/migrator.py — alembic upgrade runs in-process."""

import logging
from unittest.mock import patch

from alembic.config import Config

from main.utils.migrator import runMigrations


def failSubprocess(*args, **kwargs):
    raise AssertionError("subprocess.run must not be called")


class TestRunMigrations:
    def test_calls_alembic_upgrade_in_process(self):
        with patch("alembic.command.upgrade") as mockUpgrade, patch("subprocess.run", side_effect=failSubprocess):
            runMigrations()

        mockUpgrade.assert_called_once()
        cfg, revision = mockUpgrade.call_args.args
        assert isinstance(cfg, Config)
        assert revision == "head"
        # file-less Config keeps env.py from calling fileConfig() and disabling app loggers
        assert cfg.config_file_name is None
        assert cfg.get_main_option("script_location").endswith("migrations")

    def test_logs_error_on_failure(self, caplog):
        with (
            caplog.at_level(logging.ERROR, logger="main.utils.migrator"),
            patch("alembic.command.upgrade", side_effect=RuntimeError("boom")),
            patch("subprocess.run", side_effect=failSubprocess),
        ):
            runMigrations()

        assert "Failed to execute migrations" in caplog.text

    def test_logs_success(self, caplog):
        with (
            caplog.at_level(logging.INFO, logger="main.utils.migrator"),
            patch("alembic.command.upgrade"),
            patch("subprocess.run", side_effect=failSubprocess),
        ):
            runMigrations()

        assert "Successfully updated database" in caplog.text
