import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from host import board_sync, watch_board


class BoardSyncTests(unittest.TestCase):
    def test_sync_returns_only_new_fit_files(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            port = Mock()

            def fetch_file(_port, filename, destination):
                if filename == "workouts.json":
                    destination.write_text("{}")
                elif filename == "new.fit":
                    destination.write_bytes(b"fit")

            with patch.object(board_sync, "DATA", data), patch.object(board_sync.serial, "Serial", return_value=port), patch.object(board_sync, "fetch_file", side_effect=fetch_file), patch.object(board_sync, "fit_filenames", return_value=["new.fit", "old.fit"]):
                (data / "old.fit").write_bytes(b"existing")
                downloaded = board_sync.sync()
                self.assertTrue((data / "new.fit").exists())

        self.assertEqual(downloaded, ["new.fit"])

    def test_partial_sync_keeps_downloaded_files_on_error(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            port = Mock()

            def fetch_file(_port, filename, destination):
                if filename == "workouts.json":
                    destination.write_text("{}")
                elif filename == "first.fit":
                    destination.write_bytes(b"fit")
                else:
                    raise board_sync.BoardSyncError("transfer failed")

            with patch.object(board_sync, "DATA", data), patch.object(board_sync.serial, "Serial", return_value=port), patch.object(board_sync, "fetch_file", side_effect=fetch_file), patch.object(board_sync, "fit_filenames", return_value=["first.fit", "second.fit"]):
                with self.assertRaises(board_sync.BoardSyncError) as raised:
                    board_sync.sync()

        self.assertEqual(raised.exception.downloaded_files, ("first.fit",))


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/tmp/ride-ledger-test")
        self.python = Path("/tmp/ride-ledger-python")
        self.weather = Path("/tmp/ride-ledger-weather")

    def test_empty_sync_uses_regular_retry_and_skips_weather(self):
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run") as run, patch.object(watch_board, "RETRY_SECONDS", 60):
            delay = watch_board.sync_cycle(self.root, self.python, self.weather)

        self.assertEqual(delay, 60)
        run.assert_not_called()

    def test_new_files_run_targeted_weather_and_use_cooldown(self):
        weather_result = Mock(returncode=0)
        with patch.object(watch_board, "sync_board", return_value=["one.fit", "two.fit"]), patch.object(watch_board.subprocess, "run", return_value=weather_result) as run, patch.object(watch_board, "COOLDOWN_SECONDS", 3600):
            delay = watch_board.sync_cycle(self.root, self.python, self.weather)

        self.assertEqual(delay, 3600)
        run.assert_called_once_with([str(self.python), str(self.weather), "one.fit", "two.fit"], cwd=self.root)

    def test_partial_download_error_still_uses_cooldown(self):
        error = board_sync.BoardSyncError("second file failed", ["one.fit"])
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=1)) as run, patch.object(watch_board, "COOLDOWN_SECONDS", 3600):
            delay = watch_board.sync_cycle(self.root, self.python, self.weather)

        self.assertEqual(delay, 3600)
        run.assert_called_once_with([str(self.python), str(self.weather), "one.fit"], cwd=self.root)


if __name__ == "__main__":
    unittest.main()
