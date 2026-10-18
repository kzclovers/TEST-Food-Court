"""Headless smoke tests that drive main.Game through full play sessions.

Runs pygame with the dummy video/audio drivers so it works in CI and on
machines without a display.
"""

import os
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


@unittest.skipUnless(PYGAME_AVAILABLE, "pygame-ce is not installed")
class GameSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        import progress as progress_module

        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_path = progress_module.DESKTOP_SAVE_PATH
        progress_module.DESKTOP_SAVE_PATH = os.path.join(self._tmpdir.name, "save.json")

        import main

        self.main = main
        self.game = main.Game()
        self.canvas = pygame.Surface((1280, 720))

    def tearDown(self):
        import progress as progress_module

        progress_module.DESKTOP_SAVE_PATH = self._original_path
        self._tmpdir.cleanup()

    def _run_until(self, target_state, max_steps, answer_correct):
        steps = 0
        while self.game.state != target_state and steps < max_steps:
            steps += 1
            state = self.game.state
            if state == "MENU":
                self.game._open_level_select()
            elif state == "LEVEL_SELECT":
                self.game._select_level(1)
            elif state == "INTRO":
                self.game.on_continue()
            elif state == "TEACHING":
                self.game.on_add_to_dictionary()
            elif state == "GAMEPLAY":
                self.game.resolve_answer(answer_correct, timeout=False)
            elif state == "FEEDBACK":
                self.game.update(game_rules_hold())
            elif state == "GAVEL":
                self.game.update(2.0)
            self.game.layout_buttons()
            self.game.draw(self.canvas)
        return steps

    def test_answering_correctly_completes_the_level(self):
        steps = self._run_until("LEVEL_COMPLETE", max_steps=500, answer_correct=True)
        self.assertEqual(self.game.state, "LEVEL_COMPLETE")
        self.assertLess(steps, 500)
        self.assertEqual(len(self.game.progress.dictionary_ids), 6)
        self.assertEqual(len(self.game.progress.mastered_ids), 6)

    def test_answering_incorrectly_fails_the_level(self):
        steps = self._run_until("LEVEL_FAILED", max_steps=500, answer_correct=False)
        self.assertEqual(self.game.state, "LEVEL_FAILED")
        self.assertLess(steps, 500)
        self.assertEqual(self.game.health, 0)

    def test_infinite_mode_ends_and_records_best_time(self):
        self._run_until("LEVEL_COMPLETE", max_steps=500, answer_correct=True)
        self.game._replay_infinite()
        steps = self._run_until("INFINITE_RESULTS", max_steps=2000, answer_correct=False)
        self.assertEqual(self.game.state, "INFINITE_RESULTS")
        self.assertLess(steps, 2000)
        self.assertIn(self.game.level, self.game.progress.infinite_best_seconds)

    def test_dictionary_and_settings_overlays_do_not_crash(self):
        self._run_until("LEVEL_COMPLETE", max_steps=500, answer_correct=True)
        self.game._open_dictionary()
        self.game.layout_buttons()
        self.game.draw(self.canvas)
        self.game._next_page()
        self.game.draw(self.canvas)
        self.game._close_dictionary()

        self.game._open_settings()
        self.game.layout_buttons()
        self.game.draw(self.canvas)
        self.game._ask_reset()
        self.game.layout_buttons()
        self.game.draw(self.canvas)
        self.game._confirm_reset()
        self.assertEqual(self.game.progress.dictionary_ids, set())
        self.assertEqual(self.game.state, "MENU")

    def test_window_to_virtual_maps_center_to_center(self):
        vx, vy = self.main.window_to_virtual((640, 360), (1280, 720))
        self.assertAlmostEqual(vx, 640)
        self.assertAlmostEqual(vy, 360)

    def test_game_starts_at_the_main_menu(self):
        self.assertEqual(self.game.state, "MENU")

    def test_level_select_keeps_unauthored_levels_locked(self):
        self.game._open_level_select()
        self.assertEqual(self.game.state, "LEVEL_SELECT")
        self.game._select_level(2)
        self.assertEqual(self.game.state, "LEVEL_SELECT")
        self.game._select_level(3)
        self.assertEqual(self.game.state, "LEVEL_SELECT")

    def test_menu_navigation_round_trip(self):
        self.game._open_how_to_play()
        self.assertEqual(self.game.state, "HOW_TO_PLAY")
        self.game.draw(self.canvas)
        self.game._go_menu()
        self.assertEqual(self.game.state, "MENU")

        self.game._open_settings()
        self.assertEqual(self.game.state, "SETTINGS")
        self.game.draw(self.canvas)
        self.game._close_settings()
        self.assertEqual(self.game.state, "MENU")

    def test_dialogue_centers_then_moves_before_papers_appear(self):
        self.game._open_level_select()
        self.game._select_level(1)
        self.game.on_continue()
        self.game.on_add_to_dictionary()

        self.assertEqual(self.game.state, "GAMEPLAY")
        self.assertEqual(self.game.dialogue_phase, "CENTER")
        self.assertEqual(self.game.papers, [])
        self.game.draw(self.canvas)

        self.game.update(self.main.DIALOGUE_CENTER_SECONDS + 0.01)
        self.assertEqual(self.game.dialogue_phase, "MOVING")
        self.assertEqual(self.game.papers, [])

        self.game.update(self.main.DIALOGUE_MOVE_SECONDS + 0.01)
        self.assertEqual(self.game.dialogue_phase, "DONE")
        self.assertGreater(len(self.game.papers), 0)
        self.assertAlmostEqual(self.game.timer, self.game.timer_max)

    def test_clicking_during_dialogue_phase_is_ignored(self):
        self.game._open_level_select()
        self.game._select_level(1)
        self.game.on_continue()
        self.game.on_add_to_dictionary()
        self.assertEqual(self.game.dialogue_phase, "CENTER")

        self.game.handle_click((640, 300))
        self.assertEqual(self.game.state, "GAMEPLAY")
        self.assertFalse(self.game.answered)


def game_rules_hold():
    import game_rules

    return game_rules.FEEDBACK_HOLD_SECONDS + 0.1


if __name__ == "__main__":
    unittest.main()
