"""Food Court -- Level 1 prototype.

Run on desktop with `python main.py`. Packaged for the browser with
Pygbag (see README.md). This milestone implements the Level 1 encounter
against the Vegetable Peeler end to end: gradual fallacy teaching,
mastery-weighted quizzing on moving answer papers, health/timer/feedback,
the dictionary, level complete/failed, and infinite-mode replay. The full
main menu and later enemies are future milestones (see SPEC.md).
"""

from __future__ import annotations

import asyncio
import math
import random
from pathlib import Path

import pygame

import game_data
import game_rules
from audio import AudioManager
from game_data import FALLACIES, FALLACIES_BY_ID
from game_rules import FallacySelector
from progress import Progress

ASSET_DIR = Path(__file__).parent / "assets"
VIRTUAL_W, VIRTUAL_H = 1280, 720

BG = (60, 38, 26)
PANEL_CREAM = (241, 231, 209)
PANEL_BORDER = (120, 84, 50)
TEXT_DARK = (62, 40, 24)
BUTTON_FILL = (214, 122, 54)
BUTTON_BORDER = (150, 80, 30)
BUTTON_TEXT = (255, 246, 232)
CORRECT_COLOR = (74, 148, 86)
INCORRECT_COLOR = (178, 58, 46)
PAPER_FILL = (250, 244, 228)
PAPER_BORDER = (150, 110, 60)
CARD_WHITE = (252, 251, 247)
SPARKLE_COLOR = (214, 122, 54)
OVERLAY_DARK = (16, 10, 8)

FLASH_DURATION = 0.5
GAVEL_DURATION = 1.2
TOAST_DURATION = 3.0
FEEDBACK_ENTER_SECONDS = 0.3
FEEDBACK_EXIT_SECONDS = 0.3

PAPER_BOUNDS = pygame.Rect(230, 320, 820, 230)
CHEF_ANCHOR = (640, 300)
TOMATO_ANCHOR = (190, 560)
ENEMY_ANCHOR = (1090, 560)
CHARACTER_SIZE = 230
CHEF_SIZE = 190

# Connected-component bounding boxes (x, y, w, h) of the five individual
# carrot illustrations in carrot_heath_bar.png, widest/fullest first.
HEALTH_ICON_RECTS = [
    (193, 1145, 1044, 393),
    (248, 638, 957, 393),
    (427, 135, 851, 393),
    (1424, 285, 704, 393),
    (1594, 776, 544, 393),
]


# --- asset helpers -------------------------------------------------------


def load_image(name: str, fallback_size=(128, 128), fallback_color=(200, 120, 80)):
    path = ASSET_DIR / name
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except Exception:
        surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
        surf.fill(fallback_color)
        return surf


def slice_sheet(sheet: pygame.Surface, count: int, cell: int = 1024) -> list[pygame.Surface]:
    frames = []
    for i in range(count):
        rect = pygame.Rect(i * cell, 0, cell, cell)
        if rect.right <= sheet.get_width():
            frames.append(sheet.subsurface(rect).copy())
    return frames


def scale_square(img: pygame.Surface, size: int) -> pygame.Surface:
    return pygame.transform.smoothscale(img, (size, size))


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_panel(surf: pygame.Surface, rect: pygame.Rect, radius: int = 18) -> None:
    pygame.draw.rect(surf, PANEL_CREAM, rect, border_radius=radius)
    pygame.draw.rect(surf, PANEL_BORDER, rect, width=3, border_radius=radius)


def draw_sparkle(surf: pygame.Surface, center: tuple[int, int], size: int, color) -> None:
    """A small four-line asterisk/sparkle accent, as seen on teaching cards."""
    cx, cy = center
    for angle_deg in (0, 45, 90, 135):
        angle = math.radians(angle_deg)
        dx, dy = math.cos(angle) * size, math.sin(angle) * size
        pygame.draw.line(surf, color, (cx - dx, cy - dy), (cx + dx, cy + dy), 3)


class Button:
    __slots__ = ("rect", "label", "action", "enabled")

    def __init__(self, rect: pygame.Rect, label: str, action, enabled: bool = True):
        self.rect = rect
        self.label = label
        self.action = action
        self.enabled = enabled

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        fill = BUTTON_FILL if self.enabled else (150, 130, 110)
        border = BUTTON_BORDER if self.enabled else (110, 95, 80)
        pygame.draw.rect(surf, fill, self.rect, border_radius=14)
        pygame.draw.rect(surf, border, self.rect, width=3, border_radius=14)
        label = font.render(self.label, True, BUTTON_TEXT)
        surf.blit(label, label.get_rect(center=self.rect.center))


class Paper:
    def __init__(self, text: str, is_correct: bool, bounds: pygame.Rect, rng: random.Random):
        self.text = text
        self.is_correct = is_correct
        self.w, self.h = 196, 64
        self.x = rng.uniform(bounds.left, max(bounds.left, bounds.right - self.w))
        self.y = rng.uniform(bounds.top, max(bounds.top, bounds.bottom - self.h))
        angle = rng.uniform(0, 2 * math.pi)
        speed = rng.uniform(55, 100)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.bounds = bounds

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x < self.bounds.left:
            self.x = self.bounds.left
            self.vx *= -1
        elif self.x + self.w > self.bounds.right:
            self.x = self.bounds.right - self.w
            self.vx *= -1
        if self.y < self.bounds.top:
            self.y = self.bounds.top
            self.vy *= -1
        elif self.y + self.h > self.bounds.bottom:
            self.y = self.bounds.bottom - self.h
            self.vy *= -1

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        r = self.rect()
        pygame.draw.rect(surf, PAPER_FILL, r, border_radius=10)
        pygame.draw.rect(surf, PAPER_BORDER, r, width=2, border_radius=10)
        lines = wrap_text(self.text, font, r.width - 14)[:3]
        total_h = len(lines) * (font.get_height() - 2)
        y = r.centery - total_h // 2
        for line in lines:
            label = font.render(line, True, TEXT_DARK)
            surf.blit(label, label.get_rect(center=(r.centerx, y + font.get_height() // 2 - 1)))
            y += font.get_height() - 2


class Game:
    def __init__(self) -> None:
        self.rng = random.Random()
        self.audio = AudioManager()
        self.progress = Progress()
        self.selector = FallacySelector()

        self.fonts = {
            "title": pygame.font.Font(None, 54),
            "large": pygame.font.Font(None, 40),
            "body": pygame.font.Font(None, 28),
            "small": pygame.font.Font(None, 22),
            "paper": pygame.font.Font(None, 20),
        }
        self.fonts["title_bold"] = pygame.font.Font(None, 54)
        self.fonts["title_bold"].set_bold(True)
        self.fonts["body_bold"] = pygame.font.Font(None, 28)
        self.fonts["body_bold"].set_bold(True)

        self._load_assets()

        self.buttons: list[Button] = []
        self.show_dictionary = False
        self.dictionary_page = 0
        self.show_settings = False
        self.show_reset_confirm = False

        self.state = "INTRO"
        self.level = 1
        self.infinite = False
        self.health = game_rules.HEALTH_MAX
        self.fallacy_ids: list[int] = []
        self.enemy_name = ""
        self.introduced_ids: list[int] = []
        self.pending_intro_queue: list[int] = []
        self.teaching_fallacy_id: int | None = None
        self.questions_since_intro = 0
        self.question_index = 0
        self.current_fallacy_id: int | None = None
        self.current_claim = ""
        self.last_claim_for: dict[int, str] = {}
        self.papers: list[Paper] = []
        self.timer = 0.0
        self.timer_max = game_rules.QUESTION_SECONDS
        self.answered = False
        self.result_label = ""
        self.result_correct = False
        self.feedback_timer = 0.0
        self.enemy_losses = 0
        self.enemy_flash = 0.0
        self.tomato_flash = 0.0
        self.toasts: list[list] = []
        self.gavel_timer = 0.0
        self.gavel_target = "INTRO"
        self.infinite_start_ms = 0
        self.infinite_survived = 0.0
        self.infinite_is_best = False

        self.start_level(1, infinite=False)

    # -- asset loading ---------------------------------------------------

    def _load_assets(self) -> None:
        self.bg = load_image("Background.png", (VIRTUAL_W, VIRTUAL_H), (60, 38, 26))
        self.logo = load_image("LOGO_food_court.png", (600, 460), (214, 122, 54))
        self.dictionary_icon = load_image("dictionary icon.PNG", (48, 64), (214, 122, 54))

        health_sheet = load_image("carrot_heath_bar.png", (2160, 1620), (214, 122, 54))
        self.health_frames: list[pygame.Surface] = []
        target_h = 34
        for x, y, w, h in HEALTH_ICON_RECTS:
            rect = pygame.Rect(x, y, w, h).clip(health_sheet.get_rect())
            piece = health_sheet.subsurface(rect).copy()
            target_w = max(1, round(piece.get_width() * target_h / piece.get_height()))
            self.health_frames.append(pygame.transform.smoothscale(piece, (target_w, target_h)))

        peeler_sheet = load_image("Peeler_SpriteSheet.png", (1024, 1024), (200, 140, 90))
        tomato_sheet = load_image("Tomato_SpriteSheet.png", (1024, 1024), (200, 70, 60))
        chef_sheet = load_image("Chef_SpriteSheet.png", (1024, 1024), (230, 200, 170))

        self.peeler_frames = slice_sheet(peeler_sheet, 5)
        self.tomato_frames = slice_sheet(tomato_sheet, 5)
        self.chef_frames = slice_sheet(chef_sheet, 3)

        self.peeler_frames = [scale_square(f, CHARACTER_SIZE) for f in self.peeler_frames]
        self.tomato_frames = [scale_square(f, CHARACTER_SIZE) for f in self.tomato_frames]
        self.chef_frames = [scale_square(f, CHEF_SIZE) for f in self.chef_frames]

    # -- level/session setup ---------------------------------------------

    def start_level(self, level: int, infinite: bool) -> None:
        self.level = level
        self.infinite = infinite
        self.health = game_rules.HEALTH_MAX
        info = game_data.LEVELS[level]
        self.fallacy_ids = info["fallacy_ids"]
        self.enemy_name = info["enemy"]

        self.selector = FallacySelector()
        for fid in self.fallacy_ids:
            stats = self.selector.stats_for(fid)
            stats.correct = self.progress.mastery_counts.get(fid, 0)
            stats.mastered = (
                fid in self.progress.mastered_ids or stats.correct >= game_rules.MASTERY_TARGET
            )

        self.introduced_ids = [fid for fid in self.fallacy_ids if fid in self.progress.dictionary_ids]
        self.pending_intro_queue = [
            fid for fid in self.fallacy_ids if fid not in self.progress.dictionary_ids
        ]
        self.questions_since_intro = 0
        self.question_index = 0
        self.papers = []
        self.enemy_losses = 0
        self.enemy_flash = 0.0
        self.tomato_flash = 0.0
        self.toasts = []
        self.last_claim_for = {}
        self.show_dictionary = False
        self.show_settings = False
        self.show_reset_confirm = False

        if infinite:
            self.infinite_start_ms = pygame.time.get_ticks()
            if self.introduced_ids:
                self.next_question()
            else:
                self.state = "INTRO"
        else:
            self.state = "INTRO"

    def begin_first_teaching(self) -> None:
        if not self.pending_intro_queue:
            self.next_question()
            return
        self.teaching_fallacy_id = self.pending_intro_queue.pop(0)
        self.state = "TEACHING"

    def on_continue(self) -> None:
        if self.introduced_ids:
            self.next_question()
        else:
            self.begin_first_teaching()

    def on_add_to_dictionary(self) -> None:
        fid = self.teaching_fallacy_id
        if fid is None:
            return
        self.progress.add_to_dictionary(fid)
        self.introduced_ids.append(fid)
        self.questions_since_intro = 0
        self.teaching_fallacy_id = None
        self.next_question()

    # -- questions ---------------------------------------------------

    def next_question(self) -> None:
        fid = self.selector.choose(self.introduced_ids, self.rng)
        bank = game_data.claims_for(self.enemy_name, fid)
        if bank:
            last = self.last_claim_for.get(fid)
            choices = [c for c in bank if c != last] or bank
            claim = self.rng.choice(choices)
            self.last_claim_for[fid] = claim
        else:
            claim = f"({FALLACIES_BY_ID[fid].name} claim text pending for {self.enemy_name}.)"

        self.current_fallacy_id = fid
        self.current_claim = claim
        self._build_papers(fid)

        if self.infinite:
            self.timer_max = game_rules.infinite_question_seconds(self.question_index)
        else:
            self.timer_max = game_rules.QUESTION_SECONDS
        self.timer = self.timer_max
        self.answered = False
        self.state = "GAMEPLAY"

    def _build_papers(self, correct_id: int) -> None:
        wrong_count = game_rules.wrong_option_count(self.level)
        other_ids = [f.id for f in FALLACIES if f.id != correct_id]
        wrong_ids = self.rng.sample(other_ids, min(wrong_count, len(other_ids)))
        entries = [(FALLACIES_BY_ID[correct_id].name, True)]
        entries += [(FALLACIES_BY_ID[i].name, False) for i in wrong_ids]
        self.rng.shuffle(entries)
        self.papers = [Paper(text, is_correct, PAPER_BOUNDS, self.rng) for text, is_correct in entries]

    def handle_paper_click(self, pos: tuple[int, int]) -> None:
        if self.state != "GAMEPLAY" or self.answered:
            return
        for paper in self.papers:
            if paper.rect().collidepoint(pos):
                self.resolve_answer(paper.is_correct, timeout=False)
                return

    def resolve_answer(self, correct: bool, timeout: bool) -> None:
        self.answered = True
        self.papers = []
        fid = self.current_fallacy_id
        assert fid is not None
        mastery_hit = self.selector.register_answer(fid, correct)
        stats = self.selector.stats_for(fid)
        self.progress.record_mastery(fid, stats.correct)

        if correct:
            self.health = min(game_rules.HEALTH_MAX, self.health + 1)
            self.enemy_losses += 1
            self.enemy_flash = FLASH_DURATION
            self.result_label = "CORRECT"
            self.audio.play_sfx("correct")
        else:
            self.health = max(0, self.health - 1)
            self.tomato_flash = FLASH_DURATION
            self.result_label = "TIME OUT" if timeout else "INCORRECT"
            self.audio.play_sfx("incorrect")

        self.result_correct = correct
        if mastery_hit:
            self.toasts.append([f"{FALLACIES_BY_ID[fid].name} mastered!", TOAST_DURATION])
            self.audio.play_sfx("mastery")

        self.feedback_timer = game_rules.FEEDBACK_HOLD_SECONDS
        self.question_index += 1
        self.questions_since_intro += 1
        self.state = "FEEDBACK"

    def after_feedback(self) -> None:
        if self.health <= 0:
            if self.infinite:
                self.finish_infinite()
            else:
                self.start_gavel("LEVEL_FAILED")
            return

        if not self.infinite and self.selector.all_mastered(self.fallacy_ids):
            self.progress.complete_level(self.level)
            self.start_gavel("LEVEL_COMPLETE")
            return

        if (
            not self.infinite
            and self.pending_intro_queue
            and self.questions_since_intro >= game_rules.TEACHING_INTERVAL
        ):
            self.teaching_fallacy_id = self.pending_intro_queue.pop(0)
            self.questions_since_intro = 0
            self.state = "TEACHING"
            return

        self.next_question()

    def start_gavel(self, target: str) -> None:
        self.gavel_target = target
        self.gavel_timer = GAVEL_DURATION
        self.state = "GAVEL"

    def finish_infinite(self) -> None:
        survived = (pygame.time.get_ticks() - self.infinite_start_ms) / 1000.0
        self.infinite_survived = survived
        self.infinite_is_best = self.progress.record_infinite_result(self.level, survived)
        self.start_gavel("INFINITE_RESULTS")

    def reset_game(self) -> None:
        self.progress.reset()
        self.start_level(1, infinite=False)

    # -- update ---------------------------------------------------

    def update(self, dt: float) -> None:
        if self.state == "GAMEPLAY" and not self.answered:
            self.timer -= dt
            if self.timer <= 0:
                self.timer = 0
                self.resolve_answer(False, timeout=True)
            else:
                for paper in self.papers:
                    paper.update(dt)
        elif self.state == "FEEDBACK":
            self.feedback_timer -= dt
            if self.feedback_timer <= 0:
                self.after_feedback()
        elif self.state == "GAVEL":
            self.gavel_timer -= dt
            if self.gavel_timer <= 0:
                self.state = self.gavel_target

        self.enemy_flash = max(0.0, self.enemy_flash - dt)
        self.tomato_flash = max(0.0, self.tomato_flash - dt)
        for toast in self.toasts:
            toast[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]

    # -- frame emotion mapping ---------------------------------------------------

    def _enemy_frame(self) -> pygame.Surface:
        if self.enemy_flash > 0:
            return self.peeler_frames[min(4, len(self.peeler_frames) - 1)]
        idx = min(3, self.enemy_losses // 3)
        return self.peeler_frames[min(idx, len(self.peeler_frames) - 1)]

    def _tomato_frame(self) -> pygame.Surface:
        if self.tomato_flash > 0:
            return self.tomato_frames[min(4, len(self.tomato_frames) - 1)]
        idx = min(3, game_rules.HEALTH_MAX - self.health)
        return self.tomato_frames[min(idx, len(self.tomato_frames) - 1)]

    # -- button layout ---------------------------------------------------

    def layout_buttons(self) -> None:
        self.buttons = []

        if self.show_settings:
            self._layout_settings_buttons()
            return
        if self.show_dictionary:
            self._layout_dictionary_buttons()
            return

        if self.state in ("INTRO", "FEEDBACK", "LEVEL_COMPLETE", "LEVEL_FAILED", "INFINITE_RESULTS"):
            self.buttons.append(Button(pygame.Rect(1190, 16, 56, 56), "☰", self._open_dictionary))
            self.buttons.append(Button(pygame.Rect(1122, 16, 56, 56), "⚙", self._open_settings))

        if self.state == "INTRO":
            self.buttons.append(
                Button(pygame.Rect(540, 560, 200, 60), "Continue", self.on_continue)
            )
        elif self.state == "TEACHING":
            self.buttons.append(
                Button(pygame.Rect(300, 556, 680, 56), "Add To Your Dictionary", self.on_add_to_dictionary)
            )
        elif self.state == "LEVEL_COMPLETE":
            self.buttons.append(
                Button(pygame.Rect(360, 560, 260, 60), "Replay (Infinite)", self._replay_infinite)
            )
            self.buttons.append(Button(pygame.Rect(660, 560, 260, 60), "Home", self._go_home))
        elif self.state == "LEVEL_FAILED":
            self.buttons.append(Button(pygame.Rect(360, 560, 260, 60), "Try Again", self._try_again))
            self.buttons.append(Button(pygame.Rect(660, 560, 260, 60), "Home", self._go_home))
        elif self.state == "INFINITE_RESULTS":
            self.buttons.append(
                Button(pygame.Rect(360, 560, 260, 60), "Play Again", self._replay_infinite)
            )
            self.buttons.append(Button(pygame.Rect(660, 560, 260, 60), "Home", self._go_home))

    def _layout_dictionary_buttons(self) -> None:
        self.buttons.append(Button(pygame.Rect(1150, 60, 48, 48), "X", self._close_dictionary))
        entries = sorted(self.progress.dictionary_ids)
        if entries:
            self.buttons.append(Button(pygame.Rect(120, 360, 56, 56), "<", self._prev_page))
            self.buttons.append(Button(pygame.Rect(1104, 360, 56, 56), ">", self._next_page))

    def _layout_settings_buttons(self) -> None:
        self.buttons.append(Button(pygame.Rect(1150, 60, 48, 48), "X", self._close_settings))
        self.buttons.append(
            Button(
                pygame.Rect(440, 300, 400, 50),
                f"Music: {'On' if self.audio.music_on else 'Off'}",
                self._toggle_music,
            )
        )
        self.buttons.append(
            Button(
                pygame.Rect(440, 366, 400, 50),
                f"Sound Effects: {'On' if self.audio.sfx_on else 'Off'}",
                self._toggle_sfx,
            )
        )
        if self.show_reset_confirm:
            self.buttons.append(
                Button(pygame.Rect(440, 470, 190, 54), "Yes, Reset", self._confirm_reset)
            )
            self.buttons.append(
                Button(pygame.Rect(650, 470, 190, 54), "Cancel", self._cancel_reset)
            )
        else:
            self.buttons.append(
                Button(pygame.Rect(440, 470, 400, 54), "Reset Game Progress", self._ask_reset)
            )

    # -- button callbacks ---------------------------------------------------

    def _open_dictionary(self) -> None:
        self.show_dictionary = True
        self.dictionary_page = 0

    def _close_dictionary(self) -> None:
        self.show_dictionary = False

    def _prev_page(self) -> None:
        entries = sorted(self.progress.dictionary_ids)
        if entries:
            self.dictionary_page = (self.dictionary_page - 1) % len(entries)

    def _next_page(self) -> None:
        entries = sorted(self.progress.dictionary_ids)
        if entries:
            self.dictionary_page = (self.dictionary_page + 1) % len(entries)

    def _open_settings(self) -> None:
        self.show_settings = True
        self.show_reset_confirm = False

    def _close_settings(self) -> None:
        self.show_settings = False
        self.show_reset_confirm = False

    def _toggle_music(self) -> None:
        self.audio.set_music_enabled(not self.audio.music_on)

    def _toggle_sfx(self) -> None:
        self.audio.set_sfx_enabled(not self.audio.sfx_on)

    def _ask_reset(self) -> None:
        self.show_reset_confirm = True

    def _cancel_reset(self) -> None:
        self.show_reset_confirm = False

    def _confirm_reset(self) -> None:
        self.reset_game()

    def _replay_infinite(self) -> None:
        self.start_level(self.level, infinite=True)

    def _try_again(self) -> None:
        self.start_level(self.level, infinite=False)

    def _go_home(self) -> None:
        self.start_level(1, infinite=False)

    # -- event handling ---------------------------------------------------

    def handle_click(self, pos: tuple[int, int]) -> None:
        for button in self.buttons:
            if button.enabled and button.rect.collidepoint(pos):
                button.action()
                return
        if not self.show_dictionary and not self.show_settings:
            self.handle_paper_click(pos)

    # -- drawing ---------------------------------------------------

    def draw(self, surf: pygame.Surface) -> None:
        surf.blit(pygame.transform.smoothscale(self.bg, (VIRTUAL_W, VIRTUAL_H)), (0, 0))

        if self.state == "INTRO":
            self._draw_intro(surf)
        elif self.state == "TEACHING":
            self._draw_hud(surf)
            self._draw_teaching_card(surf)
        elif self.state in ("GAMEPLAY", "FEEDBACK"):
            self._draw_gameplay(surf)
        elif self.state == "GAVEL":
            self._draw_gameplay_frozen(surf)
            self._draw_gavel(surf)
        elif self.state == "LEVEL_COMPLETE":
            self._draw_result_card(surf, "LEVEL COMPLETE", CORRECT_COLOR)
        elif self.state == "LEVEL_FAILED":
            self._draw_result_card(surf, "LEVEL FAILED", INCORRECT_COLOR)
        elif self.state == "INFINITE_RESULTS":
            self._draw_infinite_results(surf)

        self._draw_toasts(surf)

        if self.show_dictionary:
            self._draw_dictionary(surf)
        elif self.show_settings:
            self._draw_settings(surf)

        for button in self.buttons:
            button.draw(surf, self.fonts["small"] if len(button.label) <= 2 else self.fonts["body"])

    def _draw_hud(self, surf: pygame.Surface) -> None:
        x = 30
        slot_w = 98
        for i, frame in enumerate(self.health_frames):
            if i >= self.health:
                faded = frame.copy()
                faded.set_alpha(70)
                surf.blit(faded, (x, 26))
            else:
                surf.blit(frame, (x, 26))
            x += slot_w

        title = f"Food Court -- Level {self.level}" + (" (Infinite)" if self.infinite else "")
        label = self.fonts["large"].render(title, True, (250, 240, 225))
        surf.blit(label, label.get_rect(midtop=(VIRTUAL_W // 2, 16)))

    def _draw_intro(self, surf: pygame.Surface) -> None:
        self._draw_hud(surf)
        logo = pygame.transform.smoothscale(self.logo, (420, int(420 * self.logo.get_height() / self.logo.get_width())))
        surf.blit(logo, logo.get_rect(center=(VIRTUAL_W // 2, 280)))
        sub = self.fonts["body"].render(
            f"{self.enemy_name} awaits in the food court.", True, (250, 240, 225)
        )
        surf.blit(sub, sub.get_rect(center=(VIRTUAL_W // 2, 480)))

    def _draw_teaching_card(self, surf: pygame.Surface) -> None:
        fid = self.teaching_fallacy_id
        if fid is None:
            return
        fallacy = FALLACIES_BY_ID[fid]

        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((*OVERLAY_DARK, 190))
        surf.blit(overlay, (0, 0))

        card = pygame.Rect(220, 100, 840, 520)
        pygame.draw.rect(surf, CARD_WHITE, card, border_radius=26)

        inset = 34
        for corner in (
            (card.left + inset, card.top + inset),
            (card.right - inset, card.top + inset),
            (card.left + inset, card.bottom - inset),
            (card.right - inset, card.bottom - inset),
        ):
            draw_sparkle(surf, corner, 13, SPARKLE_COLOR)

        number_text = self.fonts["title_bold"].render(f"{fallacy.id}  {fallacy.name}", True, (20, 16, 12))
        title_pos = (card.left + 64, card.top + 44)
        surf.blit(number_text, title_pos)
        if fallacy.alt_name:
            alt_text = self.fonts["body_bold"].render(f"({fallacy.alt_name})", True, (20, 16, 12))
            alt_x = title_pos[0] + number_text.get_width() + 16
            alt_y = title_pos[1] + (number_text.get_height() - alt_text.get_height()) // 2
            surf.blit(alt_text, (alt_x, alt_y))

        y = card.top + 118
        for line in wrap_text(fallacy.definition, self.fonts["body"], card.width - 128):
            label = self.fonts["body"].render(line, True, (40, 34, 28))
            surf.blit(label, (card.left + 64, y))
            y += self.fonts["body"].get_height() + 2
        y += 28

        example_header = self.fonts["body_bold"].render("Example", True, (20, 16, 12))
        surf.blit(example_header, (card.left + 64, y))
        y += example_header.get_height() + 10

        examples = game_data.claims_for(self.enemy_name, fid)[:2]
        for claim in examples:
            for line in wrap_text(f"“{claim}”", self.fonts["body"], card.width - 128):
                label = self.fonts["body"].render(line, True, (40, 34, 28))
                surf.blit(label, (card.left + 64, y))
                y += self.fonts["body"].get_height() + 2
            y += 14

    def _draw_gameplay(self, surf: pygame.Surface) -> None:
        self._draw_hud(surf)

        chef = self.chef_frames[0]
        surf.blit(chef, chef.get_rect(midbottom=CHEF_ANCHOR))

        tomato = self._tomato_frame()
        surf.blit(tomato, tomato.get_rect(midbottom=TOMATO_ANCHOR))

        enemy = pygame.transform.flip(self._enemy_frame(), True, False)
        surf.blit(enemy, enemy.get_rect(midbottom=ENEMY_ANCHOR))

        if self.state == "GAMEPLAY":
            bar_w = 300
            pct = 0 if self.timer_max <= 0 else max(0.0, self.timer / self.timer_max)
            bar_rect = pygame.Rect(0, 0, bar_w, 16)
            bar_rect.midtop = (VIRTUAL_W // 2, 70)
            pygame.draw.rect(surf, (90, 60, 40), bar_rect, border_radius=8)
            fill_rect = pygame.Rect(bar_rect.left, bar_rect.top, int(bar_w * pct), bar_rect.height)
            pygame.draw.rect(surf, (235, 190, 90), fill_rect, border_radius=8)
            pygame.draw.rect(surf, PANEL_BORDER, bar_rect, width=2, border_radius=8)

            for paper in self.papers:
                paper.draw(surf, self.fonts["paper"])

        voice_box = pygame.Rect(60, 580, 1160, 110)
        draw_panel(surf, voice_box, radius=16)
        speaker = self.fonts["body"].render(f"{self.enemy_name}:", True, PANEL_BORDER)
        surf.blit(speaker, (voice_box.left + 24, voice_box.top + 12))
        for i, line in enumerate(wrap_text(self.current_claim, self.fonts["body"], voice_box.width - 48)[:3]):
            label = self.fonts["body"].render(line, True, TEXT_DARK)
            surf.blit(label, (voice_box.left + 24, voice_box.top + 44 + i * 26))

        if self.state == "FEEDBACK":
            self._draw_feedback_banner(surf)

    def _draw_gameplay_frozen(self, surf: pygame.Surface) -> None:
        self.state, saved = "GAMEPLAY", self.state
        self.papers = []
        self._draw_gameplay(surf)
        self.state = saved

    def _draw_feedback_banner(self, surf: pygame.Surface) -> None:
        color = CORRECT_COLOR if self.result_correct else INCORRECT_COLOR
        total = game_rules.FEEDBACK_HOLD_SECONDS
        elapsed = max(0.0, total - self.feedback_timer)

        if elapsed < FEEDBACK_ENTER_SECONDS:
            t = elapsed / FEEDBACK_ENTER_SECONDS
            x_offset = (1 - t) * VIRTUAL_W
        elif elapsed > total - FEEDBACK_EXIT_SECONDS:
            t = (elapsed - (total - FEEDBACK_EXIT_SECONDS)) / FEEDBACK_EXIT_SECONDS
            x_offset = -t * VIRTUAL_W
        else:
            x_offset = 0.0

        bar_h = 120
        banner = pygame.Rect(int(x_offset), 0, VIRTUAL_W, bar_h)
        banner.centery = 330
        pygame.draw.rect(surf, color, banner)
        pygame.draw.rect(surf, (255, 255, 255), banner, width=4)
        label = self.fonts["title_bold"].render(self.result_label, True, (255, 255, 255))
        surf.blit(label, label.get_rect(center=banner.center))

    def _draw_gavel(self, surf: pygame.Surface) -> None:
        progress = 1 - max(0.0, self.gavel_timer) / GAVEL_DURATION
        frame_idx = min(len(self.chef_frames) - 1, int(progress * len(self.chef_frames)))
        chef = self.chef_frames[frame_idx]
        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((20, 12, 8, 140))
        surf.blit(overlay, (0, 0))
        big = pygame.transform.smoothscale(chef, (chef.get_width() * 2, chef.get_height() * 2))
        surf.blit(big, big.get_rect(center=(VIRTUAL_W // 2, VIRTUAL_H // 2)))

    def _draw_result_card(self, surf: pygame.Surface, title: str, color: tuple) -> None:
        self._draw_hud(surf)
        card = pygame.Rect(340, 220, 600, 300)
        draw_panel(surf, card, radius=22)
        label = self.fonts["title"].render(title, True, color)
        surf.blit(label, label.get_rect(center=(card.centerx, card.top + 80)))
        if title == "LEVEL COMPLETE":
            sub = f"All {len(self.fallacy_ids)} fallacies mastered!"
        else:
            sub = "Health depleted -- give it another go."
        sub_label = self.fonts["body"].render(sub, True, TEXT_DARK)
        surf.blit(sub_label, sub_label.get_rect(center=(card.centerx, card.top + 150)))

    def _draw_infinite_results(self, surf: pygame.Surface) -> None:
        self._draw_hud(surf)
        card = pygame.Rect(340, 200, 600, 340)
        draw_panel(surf, card, radius=22)
        label = self.fonts["title"].render("INFINITE MODE", True, TEXT_DARK)
        surf.blit(label, label.get_rect(center=(card.centerx, card.top + 60)))
        survived = self.fonts["large"].render(
            f"Survived: {self.infinite_survived:.1f}s", True, TEXT_DARK
        )
        surf.blit(survived, survived.get_rect(center=(card.centerx, card.top + 130)))
        best = self.progress.infinite_best_seconds.get(self.level, 0.0)
        best_label = self.fonts["body"].render(f"Best: {best:.1f}s", True, TEXT_DARK)
        surf.blit(best_label, best_label.get_rect(center=(card.centerx, card.top + 175)))
        if self.infinite_is_best:
            new_best = self.fonts["body"].render("New best!", True, CORRECT_COLOR)
            surf.blit(new_best, new_best.get_rect(center=(card.centerx, card.top + 210)))

    def _draw_toasts(self, surf: pygame.Surface) -> None:
        y = 90
        for text, remaining in self.toasts:
            alpha = 255 if remaining > 0.6 else int(255 * (remaining / 0.6))
            box = pygame.Rect(0, 0, 420, 44)
            box.midtop = (VIRTUAL_W // 2, y)
            panel = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (235, 190, 90, alpha), panel.get_rect(), border_radius=12)
            pygame.draw.rect(panel, (150, 110, 40, alpha), panel.get_rect(), width=2, border_radius=12)
            surf.blit(panel, box)
            label = self.fonts["body"].render(text, True, TEXT_DARK)
            label.set_alpha(alpha)
            surf.blit(label, label.get_rect(center=box.center))
            y += 50

    def _draw_dictionary(self, surf: pygame.Surface) -> None:
        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((10, 6, 4, 160))
        surf.blit(overlay, (0, 0))

        book = pygame.Rect(260, 100, 760, 500)
        draw_panel(surf, book, radius=24)

        entries = sorted(self.progress.dictionary_ids)
        title = self.fonts["title"].render("Fallacy Dictionary", True, TEXT_DARK)
        surf.blit(title, title.get_rect(center=(book.centerx, book.top + 44)))

        if not entries:
            empty = self.fonts["body"].render("No fallacies collected yet.", True, TEXT_DARK)
            surf.blit(empty, empty.get_rect(center=book.center))
            return

        self.dictionary_page %= len(entries)
        fid = entries[self.dictionary_page]
        fallacy = FALLACIES_BY_ID[fid]

        y = book.top + 110
        name_text = fallacy.name + (f" ({fallacy.alt_name})" if fallacy.alt_name else "")
        name = self.fonts["large"].render(name_text, True, TEXT_DARK)
        surf.blit(name, (book.left + 50, y))
        y += 60

        for line in wrap_text(fallacy.definition, self.fonts["body"], book.width - 100):
            label = self.fonts["body"].render(line, True, TEXT_DARK)
            surf.blit(label, (book.left + 50, y))
            y += self.fonts["body"].get_height() + 2
        y += 16

        examples = game_data.claims_for(game_data.enemy_for_fallacy(fid), fid)[:2]
        if examples:
            header = self.fonts["body_bold"].render("Example", True, TEXT_DARK)
            surf.blit(header, (book.left + 50, y))
            y += header.get_height() + 8
            for claim in examples:
                for line in wrap_text(f"“{claim}”", self.fonts["body"], book.width - 100):
                    label = self.fonts["body"].render(line, True, TEXT_DARK)
                    surf.blit(label, (book.left + 50, y))
                    y += self.fonts["body"].get_height() + 2
                y += 14

        page_label = self.fonts["small"].render(
            f"{self.dictionary_page + 1} / {len(entries)}", True, TEXT_DARK
        )
        surf.blit(page_label, page_label.get_rect(center=(book.centerx, book.bottom - 30)))

    def _draw_settings(self, surf: pygame.Surface) -> None:
        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((10, 6, 4, 160))
        surf.blit(overlay, (0, 0))

        panel = pygame.Rect(340, 160, 600, 420)
        draw_panel(surf, panel, radius=24)
        title = self.fonts["title"].render("Settings", True, TEXT_DARK)
        surf.blit(title, title.get_rect(center=(panel.centerx, panel.top + 50)))

        if self.show_reset_confirm:
            warn = self.fonts["body"].render(
                "Erase all saved dictionary and progress?", True, INCORRECT_COLOR
            )
            surf.blit(warn, warn.get_rect(center=(panel.centerx, panel.top + 220)))


def window_to_virtual(pos: tuple[int, int], window_size: tuple[int, int]) -> tuple[int, int]:
    ww, wh = window_size
    scale = min(ww / VIRTUAL_W, wh / VIRTUAL_H)
    draw_w, draw_h = VIRTUAL_W * scale, VIRTUAL_H * scale
    offset_x = (ww - draw_w) / 2
    offset_y = (wh - draw_h) / 2
    vx = (pos[0] - offset_x) / scale if scale else 0
    vy = (pos[1] - offset_y) / scale if scale else 0
    return vx, vy


async def main() -> None:
    pygame.init()
    pygame.display.set_caption("Food Court")
    screen = pygame.display.set_mode((VIRTUAL_W, VIRTUAL_H), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    canvas = pygame.Surface((VIRTUAL_W, VIRTUAL_H))

    game = Game()
    game.layout_buttons()

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        window_size = screen.get_size()
        portrait = window_size[1] > window_size[0]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not portrait:
                vpos = window_to_virtual(event.pos, screen.get_size())
                game.handle_click(vpos)
                game.layout_buttons()

        if not portrait:
            game.update(dt)
            game.layout_buttons()

        canvas.fill(BG)
        if portrait:
            font = pygame.font.Font(None, 36)
            msg = font.render("Please rotate your device to landscape", True, (240, 230, 210))
            canvas.blit(msg, msg.get_rect(center=(VIRTUAL_W // 2, VIRTUAL_H // 2)))
        else:
            game.draw(canvas)

        scale = min(window_size[0] / VIRTUAL_W, window_size[1] / VIRTUAL_H)
        draw_w, draw_h = int(VIRTUAL_W * scale), int(VIRTUAL_H * scale)
        scaled = pygame.transform.smoothscale(canvas, (draw_w, draw_h))
        screen.fill((0, 0, 0))
        screen.blit(scaled, ((window_size[0] - draw_w) // 2, (window_size[1] - draw_h) // 2))

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
