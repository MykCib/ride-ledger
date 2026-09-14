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

    def test_reset_board_writes_reset_and_waits_for_ack(self):
        port = Mock()
        port.readline.return_value = b"OK\n"
        with patch.object(board_sync.serial, "Serial", return_value=port):
            self.assertTrue(board_sync.reset_board())
        port.write.assert_called_once_with(b"RESET\n")


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/tmp/ride-ledger-test")
        self.python = Path("/tmp/ride-ledger-python")
        self.weather = Path("/tmp/ride-ledger-weather")
        watch_board._reset_backoff()

    def tearDown(self):
        watch_board._reset_backoff()

    def test_empty_sync_skips_weather_but_heals_index(self):
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(watch_board, "RETRY_SECONDS", 60):
            delay = watch_board.sync_cycle(self.root, self.python, self.weather)

        self.assertEqual(delay, 60)
        run.assert_called_once()
        heal_cmd = run.call_args[0][0]
        self.assertIn("indexer.py", str(heal_cmd[1]))
        self.assertIn("--incremental", heal_cmd)
        self.assertNotIn(str(self.weather), [str(part) for part in heal_cmd])

    def test_new_files_run_targeted_weather_and_use_cooldown(self):
        weather_result = Mock(returncode=0)
        with patch.object(watch_board, "sync_board", return_value=["one.fit", "two.fit"]), patch.object(watch_board.subprocess, "run", return_value=weather_result) as run, patch.object(watch_board, "COOLDOWN_SECONDS", 3600):
            delay = watch_board.sync_cycle(self.root, self.python, self.weather)

        self.assertEqual(delay, 3600)
        self.assertEqual(run.call_count, 2)
        run.assert_any_call([str(self.python), str(self.weather), "one.fit", "two.fit"], cwd=self.root)

    def test_partial_download_error_still_uses_cooldown(self):
        error = board_sync.BoardSyncError("second file failed", ["one.fit"])
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=1)) as run, patch.object(watch_board, "COOLDOWN_SECONDS", 3600):
            delay = watch_board.sync_cycle(self.root, self.python, self.weather)

        self.assertEqual(delay, 3600)
        self.assertEqual(run.call_count, 2)
        run.assert_any_call([str(self.python), str(self.weather), "one.fit"], cwd=self.root)

    def test_idle_syncs_back_off_and_cap(self):
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_IDLE_SECONDS", 200):
            delays = [watch_board.sync_cycle(self.root, self.python, self.weather) for _ in range(4)]

        self.assertEqual(delays, [60, 120, 200, 200])
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertIn("--incremental", call[0][0])

    def test_index_heal_failure_is_logged_but_keeps_backoff(self):
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=1)), patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_IDLE_SECONDS", 200):
            delays = [watch_board.sync_cycle(self.root, self.python, self.weather) for _ in range(2)]

        self.assertEqual(delays, [60, 120])

    def test_unavailable_device_retries_quickly_up_to_its_own_cap(self):
        error = board_sync.BoardSyncError("ERR xoss-unavailable")
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_IDLE_SECONDS", 900), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 200):
            delays = [watch_board.sync_cycle(self.root, self.python, self.weather) for _ in range(4)]

        self.assertEqual(delays, [60, 120, 200, 200])

    def test_asleep_cap_is_much_lower_than_idle_cap_by_default(self):
        # Scanning an asleep device does not wake it, so unavailable retries
        # stay frequent; connecting to a reachable idle device backs off harder.
        with patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_IDLE_SECONDS", 900), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 120):
            self.assertEqual(watch_board._backoff_delay(10, cap=watch_board.MAX_ASLEEP_SECONDS), 120)
            self.assertEqual(watch_board._backoff_delay(10), 900)

    def test_new_files_reset_backoff(self):
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run"), patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_IDLE_SECONDS", 200):
            watch_board.sync_cycle(self.root, self.python, self.weather)
            watch_board.sync_cycle(self.root, self.python, self.weather)
        with patch.object(watch_board, "sync_board", return_value=["one.fit"]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=0)), patch.object(watch_board, "COOLDOWN_SECONDS", 3600):
            self.assertEqual(watch_board.sync_cycle(self.root, self.python, self.weather), 3600)
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_IDLE_SECONDS", 200):
            self.assertEqual(watch_board.sync_cycle(self.root, self.python, self.weather), 60)
            run.assert_called_once()
            self.assertIn("--incremental", run.call_args[0][0])

    def test_unexpected_watcher_error_backs_off(self):
        with patch.object(watch_board, "sync_board", side_effect=RuntimeError("boom")), patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 200):
            delays = [watch_board.sync_cycle(self.root, self.python, self.weather) for _ in range(3)]

        self.assertEqual(delays, [60, 120, 200])

    def test_once_mode_runs_a_single_cycle(self):
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(watch_board, "RETRY_SECONDS", 60):
            result = watch_board.main(["--once"])

        self.assertEqual(result, 0)
        self.assertEqual(run.call_count, 1)

    def test_wedge_watchdog_reboots_bridge_after_repeated_misses(self):
        error = board_sync.BoardSyncError("ERR xoss-unavailable")
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board, "reset_board", return_value=True) as reset, patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 120), patch.object(watch_board, "BOARD_RESET_AFTER", 3):
            watch_board.sync_cycle(self.root, self.python, self.weather)
            watch_board.sync_cycle(self.root, self.python, self.weather)
            reset.assert_not_called()
            watch_board.sync_cycle(self.root, self.python, self.weather)
            reset.assert_called_once()

    def test_wedge_watchdog_ignores_unrelated_sync_errors(self):
        error = board_sync.BoardSyncError("ERR transfer-failed")
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board, "reset_board", return_value=True) as reset, patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 120), patch.object(watch_board, "BOARD_RESET_AFTER", 1):
            watch_board.sync_cycle(self.root, self.python, self.weather)

        reset.assert_not_called()

    def test_reachable_device_clears_wedge_counter(self):
        error = board_sync.BoardSyncError("ERR xoss-unavailable")
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board, "reset_board", return_value=True) as reset, patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 120), patch.object(watch_board, "BOARD_RESET_AFTER", 3):
            watch_board.sync_cycle(self.root, self.python, self.weather)
            watch_board.sync_cycle(self.root, self.python, self.weather)
        with patch.object(watch_board, "sync_board", return_value=[]), patch.object(watch_board.subprocess, "run", return_value=Mock(returncode=0)), patch.object(watch_board, "MAX_IDLE_SECONDS", 900):
            watch_board.sync_cycle(self.root, self.python, self.weather)
        with patch.object(watch_board, "sync_board", side_effect=error), patch.object(watch_board, "reset_board", return_value=True) as reset2, patch.object(watch_board, "RETRY_SECONDS", 60), patch.object(watch_board, "MAX_ASLEEP_SECONDS", 120), patch.object(watch_board, "BOARD_RESET_AFTER", 3):
            watch_board.sync_cycle(self.root, self.python, self.weather)
            reset2.assert_not_called()


if __name__ == "__main__":
    unittest.main()
