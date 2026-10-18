"""Food Court.

Run on desktop with `python main.py`. Packaged for the browser with
Pygbag (see README.md). Six levels (two per enemy) each teach three
fallacies, run a no-damage warm-up, then an official round where both
sides lose health. Infinite mode reviews everything unlocked so far.
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
from entities.chef import Chef
from entities.peeler import Peeler
from entities.tomato import Tomato
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
TOAST_DURATION = 2.0
FEEDBACK_ENTER_SECONDS = 0.3
FEEDBACK_EXIT_SECONDS = 0.3
DIALOGUE_CENTER_SECONDS = 0.1
DIALOGUE_MOVE_SECONDS = 1.0
PAGE_TURN_SECONDS = 0.65
CARDS_PER_SPREAD = 4  # two dictionary cards on each page of the open book

# Open-book art (`Untitled_Artwork 9.png`) is a square canvas. These rects
# are in that image's pixel space: the crop is the opaque book, and the
# page rects sit on the cream of each page, below the binder rings.
BOOK_CROP = pygame.Rect(162, 294, 1724, 1366)
LEFT_PAGE_SRC = pygame.Rect(250, 660, 700, 900)
RIGHT_PAGE_SRC = pygame.Rect(1102, 660, 688, 900)
BOOK_MAX = (1080, 690)

PAPER_BOUNDS = pygame.Rect(230, 320, 820, 230)
CHEF_ANCHOR = (640, 500)
TOMATO_ANCHOR = (190, 560)
ENEMY_ANCHOR = (1090, 560)
CHARACTER_SIZE = 230
CHEF_SIZE = 400

LEVEL_CIRCLE_RECTS = [pygame.Rect(70 + i * 196, 300, 160, 160) for i in range(6)]
INFINITE_BUTTON_RECT = pygame.Rect(470, 130, 340, 72)
RETURN_BUTTON_RECT = pygame.Rect(40, 28, 64, 64)
PAUSE_BUTTON_RECT = pygame.Rect(22, 16, 56, 56)
PAUSE_POPUP_RECT = pygame.Rect(440, 200, 400, 300)
INFINITE_SAVE_KEY = 0  # infinite mode is one shared run, not per level
ENEMY_SHEETS = {
    "Vegetable Peeler": "Peeler_SpriteSheet.png",
    "Knife": "Knife_SpriteSheet.png",
    "Boiling Pot": "Pot_SpriteSheet.png",
}
SETTINGS_PAPER_RECT = pygame.Rect(450, 50, 380, 600)
SETTINGS_ROW_RECTS = [pygame.Rect(500, 330, 280, 50), pygame.Rect(500, 410, 280, 50)]

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


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def book_display_size() -> tuple[int, int]:
    scale = min(BOOK_MAX[0] / BOOK_CROP.width, BOOK_MAX[1] / BOOK_CROP.height)
    return (
        max(1, int(BOOK_CROP.width * scale)),
        max(1, int(BOOK_CROP.height * scale)),
    )


def lerp_rect(a: pygame.Rect, b: pygame.Rect, t: float) -> pygame.Rect:
    t = max(0.0, min(1.0, t))
    return pygame.Rect(
        round(a.left + (b.left - a.left) * t),
        round(a.top + (b.top - a.top) * t),
        round(a.width + (b.width - a.width) * t),
        round(a.height + (b.height - a.height) * t),
    )


def draw_icon(surf: pygame.Surface, name: str, center: tuple[int, int], size: int, color) -> None:
    """Simple line icons in the mockups' style, drawn instead of image assets."""
    cx, cy = center
    s = size
    w = max(2, s // 8)
    if name == "home":
        roof = [(cx - s * 0.55, cy - s * 0.02), (cx, cy - s * 0.5), (cx + s * 0.55, cy - s * 0.02)]
        pygame.draw.lines(surf, color, False, roof, w)
        body = pygame.Rect(0, 0, round(s * 0.75), round(s * 0.55))
        body.midtop = (cx, round(cy - s * 0.12))
        pygame.draw.rect(surf, color, body, w, border_radius=3)
        door = pygame.Rect(0, 0, round(s * 0.22), round(s * 0.3))
        door.midbottom = body.midbottom
        pygame.draw.rect(surf, color, door, w)
    elif name == "return":
        r = round(s * 0.42)
        rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.arc(surf, color, rect, math.radians(-200), math.radians(110), w)
        tip = (cx - r * 0.35, cy - r)
        pygame.draw.polygon(surf, color, [
            (tip[0] - s * 0.18, tip[1]), (tip[0] + s * 0.08, tip[1] - s * 0.18), (tip[0] + s * 0.08, tip[1] + s * 0.18)
        ])
    elif name in ("next", "prev"):
        d = 1 if name == "next" else -1
        pygame.draw.line(surf, color, (cx - d * s * 0.4, cy), (cx + d * s * 0.35, cy), w)
        pygame.draw.lines(surf, color, False, [
            (cx + d * s * 0.05, cy - s * 0.32), (cx + d * s * 0.38, cy), (cx + d * s * 0.05, cy + s * 0.32)
        ], w)
    elif name == "lock":
        body = pygame.Rect(0, 0, round(s * 0.8), round(s * 0.6))
        body.midtop = (cx, round(cy - s * 0.05))
        pygame.draw.rect(surf, color, body, w, border_radius=max(2, s // 10))
        shackle = pygame.Rect(0, 0, round(s * 0.5), round(s * 0.6))
        shackle.midbottom = (cx, body.top + w)
        pygame.draw.arc(surf, color, shackle, 0, math.pi, w)
        pygame.draw.line(surf, color, (shackle.left + w // 2, shackle.centery), (shackle.left + w // 2, body.top), w)
        pygame.draw.line(surf, color, (shackle.right - w // 2 - 1, shackle.centery), (shackle.right - w // 2 - 1, body.top), w)
    elif name == "pause":
        bar = pygame.Rect(0, 0, max(4, round(s * 0.18)), round(s * 0.62))
        for dx in (-s * 0.17, s * 0.17):
            bar.center = (round(cx + dx), cy)
            pygame.draw.rect(surf, color, bar, border_radius=2)
    elif name == "check":
        pygame.draw.lines(surf, color, False, [(cx - s * 0.4, cy), (cx - s * 0.1, cy + s * 0.3), (cx + s * 0.45, cy - s * 0.35)], w + 2)
    elif name == "gear":
        r = s * 0.3
        for i in range(8):
            a = i * math.pi / 4
            pygame.draw.line(surf, color, (cx + math.cos(a) * r, cy + math.sin(a) * r),
                             (cx + math.cos(a) * s * 0.48, cy + math.sin(a) * s * 0.48), w + 2)
        pygame.draw.circle(surf, color, (cx, cy), round(r), w)
    elif name == "book":
        left = pygame.Rect(0, 0, round(s * 0.42), round(s * 0.7))
        left.topright = (cx, round(cy - s * 0.35))
        right = left.copy()
        right.topleft = (cx, left.top)
        pygame.draw.rect(surf, color, left, w, border_radius=2)
        pygame.draw.rect(surf, color, right, w, border_radius=2)


def draw_outlined_text(surf, font, text, center, fill=(255, 255, 255), outline=(60, 34, 20), width=3) -> None:
    base = font.render(text, True, outline)
    rect = base.get_rect(center=center)
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy <= width * width:
                surf.blit(base, rect.move(dx, dy))
    surf.blit(font.render(text, True, fill), rect)


def draw_paper(surf: pygame.Surface, rect: pygame.Rect, tilt: float = -2.5) -> None:
    """A slightly tilted cream sheet of paper with a soft shadow, as in the mockups."""
    sheet = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(sheet, PAPER_FILL, sheet.get_rect(), border_radius=6)
    inner = sheet.get_rect().inflate(-24, -24)
    pygame.draw.rect(sheet, (205, 190, 165), inner, 1, border_radius=4)
    shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=6)
    shadow = pygame.transform.rotate(shadow, tilt)
    sheet = pygame.transform.rotate(sheet, tilt)
    surf.blit(shadow, shadow.get_rect(center=(rect.centerx + 8, rect.centery + 10)))
    surf.blit(sheet, sheet.get_rect(center=rect.center))


def circle_portrait(sprite: pygame.Surface, diameter: int, bg=(245, 242, 236), darken: bool = False) -> pygame.Surface:
    portrait = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(portrait, bg, (diameter // 2, diameter // 2), diameter // 2)
    scale = diameter * 1.05 / max(sprite.get_width(), sprite.get_height())
    img = pygame.transform.smoothscale(
        sprite, (max(1, round(sprite.get_width() * scale)), max(1, round(sprite.get_height() * scale)))
    )
    portrait.blit(img, img.get_rect(center=(diameter // 2, round(diameter * 0.58))))
    if darken:
        shade = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        shade.fill((40, 40, 40, 170))
        portrait.blit(shade, (0, 0))
    mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (diameter // 2, diameter // 2), diameter // 2)
    portrait.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return portrait


def draw_sparkle(surf: pygame.Surface, center: tuple[int, int], size: int, color) -> None:
    """A small four-line asterisk/sparkle accent, as seen on teaching cards."""
    cx, cy = center
    for angle_deg in (0, 45, 90, 135):
        angle = math.radians(angle_deg)
        dx, dy = math.cos(angle) * size, math.sin(angle) * size
        pygame.draw.line(surf, color, (cx - dx, cy - dy), (cx + dx, cy + dy), 3)


class Button:
    """Styles: "pill" (rounded orange), "icon" (orange circle + vector icon,
    label drawn underneath as a caption), "link" (checkbox + underlined text
    on paper), "hidden" (hit area only; the screen draws the visuals)."""

    __slots__ = ("rect", "label", "action", "enabled", "radius", "style", "icon")

    def __init__(self, rect: pygame.Rect, label: str, action, enabled: bool = True, radius: int = 14,
                 style: str = "pill", icon: str = ""):
        self.rect = rect
        self.label = label
        self.action = action
        self.enabled = enabled
        self.radius = radius
        self.style = style
        self.icon = icon

    def draw(self, surf: pygame.Surface, font: pygame.font.Font) -> None:
        if self.style == "hidden":
            return
        if self.style == "icon":
            r = self.rect.width // 2
            pygame.draw.circle(surf, (120, 60, 25), (self.rect.centerx + 2, self.rect.centery + 4), r)
            pygame.draw.circle(surf, BUTTON_FILL, self.rect.center, r)
            pygame.draw.circle(surf, (245, 225, 200), self.rect.center, r - 5, 3)
            draw_icon(surf, self.icon, self.rect.center, round(r * 1.0), (255, 250, 240))
            if self.label:
                draw_outlined_text(surf, font, self.label, (self.rect.centerx, self.rect.bottom + 18), width=2)
            return
        if self.style == "link":
            box = pygame.Rect(self.rect.left, 0, 20, 20)
            box.centery = self.rect.centery
            pygame.draw.rect(surf, (90, 70, 50), box, 2, border_radius=3)
            label = font.render(self.label, True, (90, 70, 50))
            pos = label.get_rect(midleft=(box.right + 14, self.rect.centery))
            surf.blit(label, pos)
            pygame.draw.line(surf, (110, 90, 70), (pos.left, pos.bottom + 2), (self.rect.right, pos.bottom + 2), 2)
            return
        fill = BUTTON_FILL if self.enabled else (150, 130, 110)
        border = BUTTON_BORDER if self.enabled else (110, 95, 80)
        pygame.draw.rect(surf, fill, self.rect, border_radius=self.radius)
        pygame.draw.rect(surf, border, self.rect, width=3, border_radius=self.radius)
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

        # Keep the selected font files inside the project so desktop and browser
        # builds use the same Nunito faces.
        font_dir = ASSET_DIR / "Nunito" / "static"
        self.fonts = {
            "title": pygame.font.Font(str(font_dir / "Nunito-Bold.ttf"), 54),
            "large": pygame.font.Font(str(font_dir / "Nunito-Regular.ttf"), 40),
            "body": pygame.font.Font(str(font_dir / "Nunito-Regular.ttf"), 28),
            "small": pygame.font.Font(str(font_dir / "Nunito-Regular.ttf"), 22),
            "paper": pygame.font.Font(str(font_dir / "Nunito-Regular.ttf"), 20),
        }
        self.fonts["title_bold"] = pygame.font.Font(str(font_dir / "Nunito-ExtraBold.ttf"), 54)
        self.fonts["body_bold"] = pygame.font.Font(str(font_dir / "Nunito-Bold.ttf"), 28)
        self.banner_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = {}
        self.banner_font = pygame.font.Font(str(font_dir / "Nunito-ExtraBold.ttf"), 84)

        self._load_assets()

        self.buttons: list[Button] = []
        self.show_dictionary = False
        self.dictionary_page = 0  # spread index; four cards, two on each page
        self.page_anim = None
        self.zoomed_card: int | None = None
        self.zoom_t = 1.0
        self._card_cache: dict = {}
        self.review_fallacy_id: int | None = None
        self.review_clicks = 0
        self.review_age = 0.0
        self.show_reset_confirm = False
        self.pre_settings_state = "MENU"

        self.state = "MENU"
        self.level = 1
        self.infinite = False
        self.health = game_rules.HEALTH_MAX
        self.enemy_health = game_rules.OPPONENT_HEALTH_MAX
        self.fallacy_ids: list[int] = []
        self.enemy_name = ""
        self.phase = "WARMUP"  # main levels: "WARMUP" then "ROUND"
        self.teaching_ids: list[int] = []
        self.teaching_added: set[int] = set()
        self.warmup_queue: list[int] = []
        self.paused = False
        self.fail_reason = ""
        self.infinite_correct = 0
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
        self.gavel_target = "MENU"
        self.infinite_start_ms = 0
        self.infinite_survived = 0.0
        self.infinite_is_best = False
        self.dialogue_phase = "DONE"
        self.dialogue_timer = 0.0

    # -- asset loading ---------------------------------------------------

    def _load_assets(self) -> None:
        self.bg = pygame.transform.smoothscale(
            load_image("Background.png", (VIRTUAL_W, VIRTUAL_H), (60, 38, 26)), (VIRTUAL_W, VIRTUAL_H)
        )
        self.bg_faded = pygame.transform.smoothscale(
            load_image("background_faded.png", (VIRTUAL_W, VIRTUAL_H), (90, 60, 40)), (VIRTUAL_W, VIRTUAL_H)
        )
        self.logo = load_image("LOGO_food_court.png", (600, 460), (214, 122, 54))
        self.logo_small = pygame.transform.smoothscale(
            self.logo, (110, round(110 * self.logo.get_height() / self.logo.get_width()))
        )
        self.dictionary_icon = load_image("dictionary icon.PNG", (48, 64), (214, 122, 54))
        book = load_image("Untitled_Artwork 9.png", BOOK_CROP.size, (255, 247, 206))
        if book.get_width() >= BOOK_CROP.right and book.get_height() >= BOOK_CROP.bottom:
            book = book.subsurface(BOOK_CROP).copy()
        self.book_image = pygame.transform.smoothscale(book, book_display_size())
        width, height = self.book_image.get_size()
        gutter = max(10, width // 24)
        mid = width // 2
        self.page_gutter = gutter
        self.page_halves = (
            self.book_image.subsurface(pygame.Rect(0, 0, mid - gutter, height)).copy(),
            self.book_image.subsurface(pygame.Rect(mid + gutter, 0, width - mid - gutter, height)).copy(),
        )
        self.book_stitch = self.book_image.subsurface(
            pygame.Rect(mid - gutter, 0, gutter * 2, height)
        ).copy()
        # Numbered files run backwards: #18 / DictionaryCard18 is fallacy 1.
        self.dictionary_cards = {
            fid: load_image(f"DictionaryCard{19 - fid:02d}.png", (480, 390), CARD_WHITE)
            for fid in range(1, 19)
        }
        self.detail_cards = {
            fid: load_image(f"Dictionary Card/#{19 - fid:02d}.png", (602, 376), CARD_WHITE)
            for fid in range(1, 19)
        }
        self.add_cards = {
            fid: load_image(f"Add cards/#{19 - fid:02d}.png", (602, 472), CARD_WHITE)
            for fid in range(1, 19)
        }

        health_sheet = load_image("carrot_heath_bar.png", (2160, 1620), (214, 122, 54))
        self.health_frames: list[pygame.Surface] = []
        target_h = 60
        for x, y, w, h in HEALTH_ICON_RECTS:
            rect = pygame.Rect(x, y, w, h).clip(health_sheet.get_rect())
            piece = health_sheet.subsurface(rect).copy()
            target_w = max(1, round(piece.get_width() * target_h / piece.get_height()))
            self.health_frames.append(pygame.transform.smoothscale(piece, (target_w, target_h)))

        self.peeler = Peeler(ASSET_DIR / "Peeler_SpriteSheet.png")
        self.peeler_frames = self.peeler.frames
        self.tomato = Tomato(ASSET_DIR / "Tomato_SpriteSheet.png")
        self.chef = Chef(path=ASSET_DIR / "Chef_SpriteSheet.png")
        self.tomato_frames = self.tomato.frames
        self.chef_frames = self.chef.frames

        # The Peeler class only wraps a five-frame strip, so it draws every enemy.
        self.enemies = {"Vegetable Peeler": self.peeler}
        for name, sheet in ENEMY_SHEETS.items():
            if name not in self.enemies:
                try:
                    self.enemies[name] = Peeler(ASSET_DIR / sheet)
                except RuntimeError:
                    self.enemies[name] = self.peeler
        diameter = LEVEL_CIRCLE_RECTS[0].width
        self.enemy_portraits = {
            name: circle_portrait(enemy.frames[0], diameter) for name, enemy in self.enemies.items()
        }
        self.enemy_portraits_locked = {
            name: circle_portrait(enemy.frames[0], diameter, bg=(70, 70, 70), darken=True)
            for name, enemy in self.enemies.items()
        }

        self.tomato_frames = [scale_square(f, CHARACTER_SIZE) for f in self.tomato_frames]
        self.chef_frames = [
            pygame.transform.smoothscale(
                frame,
                (
                    max(1, round(frame.get_width() * CHEF_SIZE / frame.get_height())),
                    CHEF_SIZE,
                ),
            )
            for frame in self.chef_frames
        ]

    # -- level/session setup ---------------------------------------------

    def _reset_session(self) -> None:
        self.health = game_rules.HEALTH_MAX
        self.enemy_health = game_rules.OPPONENT_HEALTH_MAX
        self.selector = FallacySelector()
        for fid in range(1, len(FALLACIES) + 1):
            stats = self.selector.stats_for(fid)
            stats.correct = self.progress.mastery_counts.get(fid, 0)
            stats.mastered = (
                fid in self.progress.mastered_ids or stats.correct >= game_rules.MASTERY_TARGET
            )
        self.question_index = 0
        self.infinite_correct = 0
        self.papers = []
        self.enemy_losses = 0
        self.enemy_flash = 0.0
        self.tomato_flash = 0.0
        self.toasts = []
        self.last_claim_for = {}
        self.show_dictionary = False
        self.page_anim = None
        self.zoomed_card = None
        self.review_fallacy_id = None
        self.review_clicks = 0
        self.review_age = 0.0
        self.show_reset_confirm = False
        self.paused = False
        self.fail_reason = ""
        self.dialogue_phase = "DONE"
        self.dialogue_timer = 0.0

    def start_level(self, level: int) -> None:
        """Main level: meet all three new fallacies, warm up, then fight."""
        self._reset_session()
        self.level = level
        self.infinite = False
        self.fallacy_ids = game_data.LEVELS[level]["fallacy_ids"]
        self.enemy_name = game_data.enemy_for_level(level)
        self.teaching_ids = list(self.fallacy_ids)
        self.teaching_added = set()
        self.warmup_queue = []
        self.phase = "WARMUP"
        self.state = "TEACHING"

    def start_infinite(self) -> None:
        """Endless review of unlocked fallacies against beaten enemies."""
        self._reset_session()
        self.infinite = True
        self.phase = "ROUND"
        self.fallacy_ids = self._infinite_fallacy_ids()
        self.infinite_start_ms = pygame.time.get_ticks()
        self.next_question()

    def _completed_enemies(self) -> list[str]:
        names = [game_data.enemy_for_level(lvl) for lvl in sorted(self.progress.completed_levels)
                 if lvl in game_data.LEVELS]
        return list(dict.fromkeys(names))

    def _infinite_fallacy_ids(self) -> list[int]:
        return sorted(self.progress.dictionary_ids)

    def _infinite_available(self) -> bool:
        return bool(self._completed_enemies()) and bool(self._infinite_fallacy_ids())

    def _quizzable_ids(self) -> list[int]:
        if self.infinite:
            return self._infinite_fallacy_ids()
        if self.phase == "WARMUP":
            return self.warmup_queue[:1]
        # Official round: everything unlocked up to and including this level.
        newest = max(self.fallacy_ids)
        return [fid for fid in sorted(self.progress.dictionary_ids) if fid <= newest] or list(self.fallacy_ids)

    def on_add_to_dictionary(self, fid: int | None = None) -> None:
        """Collect one of the three new cards; once all are in, warm up."""
        if self.state != "TEACHING":
            return
        if fid is None:
            remaining = [f for f in self.teaching_ids if f not in self.teaching_added]
            if not remaining:
                return
            fid = remaining[0]
        if fid not in self.teaching_ids or fid in self.teaching_added:
            return
        self.teaching_added.add(fid)
        self.progress.add_to_dictionary(fid)
        self.audio.play_sfx("dictionary")
        if len(self.teaching_added) == len(self.teaching_ids):
            self.warmup_queue = list(self.teaching_ids)
            self.rng.shuffle(self.warmup_queue)
            self.phase = "WARMUP"
            self.toasts.append(["Warm-up: no damage yet!", TOAST_DURATION])
            self.next_question()

    # -- questions ---------------------------------------------------

    def _pick_infinite_enemy(self, fid: int) -> str:
        enemies = self._completed_enemies() or [game_data.enemy_for_fallacy(fid)]
        with_claims = [name for name in enemies if game_data.claims_for(name, fid)]
        return self.rng.choice(with_claims or enemies)

    def next_question(self) -> None:
        pool = self._quizzable_ids()
        if not pool:
            return
        if self.phase == "WARMUP" and not self.infinite:
            fid = pool[0]
        else:
            fid = self.selector.choose(pool, self.rng)
        if self.infinite:
            self.enemy_name = self._pick_infinite_enemy(fid)
        bank = game_data.claims_for(self.enemy_name, fid) or game_data.claims_for(
            game_data.enemy_for_fallacy(fid), fid
        )
        if bank:
            last = self.last_claim_for.get(fid)
            choices = [c for c in bank if c != last] or bank
            claim = self.rng.choice(choices)
            self.last_claim_for[fid] = claim
        else:
            claim = f"({FALLACIES_BY_ID[fid].name} claim text pending for {self.enemy_name}.)"

        self.current_fallacy_id = fid
        self.current_claim = claim
        self.papers = []

        if self.infinite:
            self.timer_max = game_rules.infinite_question_seconds(self.question_index)
        else:
            self.timer_max = game_rules.QUESTION_SECONDS
        self.timer = self.timer_max
        self.answered = False
        self.dialogue_phase = "CENTER"
        self.dialogue_timer = DIALOGUE_CENTER_SECONDS
        self.state = "GAMEPLAY"

    def _advance_dialogue(self, dt: float) -> None:
        """Center claim text for a beat, slide it down, then reveal papers.

        The answer timer only starts once the papers are built, in the
        DONE phase (see update()).
        """
        self.dialogue_timer -= dt
        if self.dialogue_timer > 0:
            return
        if self.dialogue_phase == "CENTER":
            self.dialogue_phase = "MOVING"
            self.dialogue_timer = DIALOGUE_MOVE_SECONDS
        elif self.dialogue_phase == "MOVING":
            self.dialogue_phase = "DONE"
            self._build_papers(self.current_fallacy_id)
            self.timer = self.timer_max

    def _build_papers(self, correct_id: int) -> None:
        if self.infinite:
            wrong_count = game_rules.infinite_option_count(self.infinite_correct) - 1
        else:
            wrong_count = game_rules.wrong_option_count(self.level)
        other_ids = [f.id for f in FALLACIES if f.id != correct_id]
        wrong_ids = self.rng.sample(other_ids, min(wrong_count, len(other_ids)))
        entries = [(FALLACIES_BY_ID[correct_id].name, True)]
        entries += [(FALLACIES_BY_ID[i].name, False) for i in wrong_ids]
        self.rng.shuffle(entries)
        self.papers = [Paper(text, is_correct, PAPER_BOUNDS, self.rng) for text, is_correct in entries]

    def handle_paper_click(self, pos: tuple[int, int]) -> None:
        if self.state != "GAMEPLAY" or self.answered or self.dialogue_phase != "DONE":
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

        warmup = self.phase == "WARMUP" and not self.infinite
        if correct:
            if self.infinite:
                # Infinite mode keeps the old rule: correct answers heal.
                self.health = min(game_rules.HEALTH_MAX, self.health + 1)
                self.infinite_correct += 1
            elif warmup:
                if self.warmup_queue and self.warmup_queue[0] == fid:
                    self.warmup_queue.pop(0)
            else:
                self.enemy_health = max(0, self.enemy_health - 1)
            self.enemy_losses += 1
            self.enemy_flash = FLASH_DURATION
            self.result_label = "CORRECT"
            self.review_fallacy_id = None
            self.review_clicks = 0
            self.audio.play_sfx("correct")
        else:
            # Warm-up misses cost nothing; the same fallacy is asked again.
            if not warmup:
                self.health = max(0, self.health - 1)
            self.tomato_flash = FLASH_DURATION
            self.result_label = "TIME OUT" if timeout else "INCORRECT"
            # Show the matching dictionary card. It is not collected.
            self.review_fallacy_id = fid
            self.review_clicks = 0
            self.review_age = 0.0
            self.audio.play_sfx("incorrect")

        self.result_correct = correct
        if mastery_hit:
            self.toasts.append([f"{FALLACIES_BY_ID[fid].name} mastered!", TOAST_DURATION])
            self.audio.play_sfx("mastery")

        self.feedback_timer = game_rules.FEEDBACK_HOLD_SECONDS
        self.question_index += 1
        self.state = "FEEDBACK"

    def _ack_review_card(self) -> None:
        """A wrong-answer card stays up until the player clicks it twice."""
        if self.state != "FEEDBACK" or self.review_fallacy_id is None:
            return
        self.review_clicks += 1
        if self.review_clicks >= 2:
            self.after_feedback()

    def after_feedback(self) -> None:
        self.review_fallacy_id = None
        self.review_clicks = 0
        if self.health <= 0:
            if self.infinite:
                self.finish_infinite()
            else:
                self.fail_reason = "Health depleted -- give it another go."
                self.start_gavel("LEVEL_FAILED")
            return

        if not self.infinite and self.enemy_health <= 0:
            self.progress.complete_level(self.level)
            self.start_gavel("LEVEL_COMPLETE")
            return

        if not self.infinite and self.phase == "WARMUP" and not self.warmup_queue:
            self.phase = "ROUND"
            self.toasts.append(["Official round -- fight!", TOAST_DURATION])

        self.next_question()

    def start_gavel(self, target: str) -> None:
        self.gavel_target = target
        self.gavel_timer = GAVEL_DURATION
        self.state = "GAVEL"

    def finish_infinite(self) -> None:
        survived = (pygame.time.get_ticks() - self.infinite_start_ms) / 1000.0
        self.infinite_survived = survived
        self.infinite_is_best = self.progress.record_infinite_result(INFINITE_SAVE_KEY, survived)
        self.start_gavel("INFINITE_RESULTS")

    def reset_game(self) -> None:
        self.progress.reset()
        self.state = "MENU"

    # -- pause ---------------------------------------------------

    def _can_pause(self) -> bool:
        return self.state in ("TEACHING", "GAMEPLAY", "FEEDBACK") and not self.show_dictionary

    def _pause(self) -> None:
        if self._can_pause():
            self.paused = True

    def _resume(self) -> None:
        self.paused = False

    def _exit_level(self) -> None:
        """Leaving a main level counts as failing it; leaving infinite mode is silent."""
        self.paused = False
        self.papers = []
        self.review_fallacy_id = None
        if self.infinite:
            self.state = "LEVEL_SELECT"
        else:
            self.fail_reason = "You left the courtroom."
            self.state = "LEVEL_FAILED"

    # -- update ---------------------------------------------------

    def update(self, dt: float) -> None:
        if self.paused:
            return
        if self.state == "GAMEPLAY" and not self.answered:
            if self.dialogue_phase != "DONE":
                self._advance_dialogue(dt)
            else:
                self.timer -= dt
                if self.timer <= 0:
                    self.timer = 0
                    self.resolve_answer(False, timeout=True)
                else:
                    for paper in self.papers:
                        paper.update(dt)
        elif self.state == "FEEDBACK":
            if self.review_fallacy_id is not None:
                self.review_age += dt
            else:
                self.feedback_timer -= dt
                if self.feedback_timer <= 0:
                    self.after_feedback()
        elif self.state == "GAVEL":
            self.gavel_timer -= dt
            if self.gavel_timer <= 0:
                self.state = self.gavel_target

        if self.page_anim is not None:
            self.page_anim["t"] += dt / PAGE_TURN_SECONDS
            if self.page_anim["t"] >= 1.0:
                self.dictionary_page = self.page_anim["target"]
                self.page_anim = None

        if self.zoomed_card is not None:
            self.zoom_t = min(1.0, self.zoom_t + dt / 0.18)

        self.enemy_flash = max(0.0, self.enemy_flash - dt)
        self.tomato_flash = max(0.0, self.tomato_flash - dt)
        for toast in self.toasts:
            toast[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]

    # -- frame emotion mapping ---------------------------------------------------

    def _enemy_frame_index(self) -> int:
        if self.enemy_flash > 0:
            return 4
        if self.infinite:
            return min(3, self.enemy_losses // 3)
        return min(3, game_rules.OPPONENT_HEALTH_MAX - self.enemy_health)

    def _tomato_frame(self) -> pygame.Surface:
        if self.tomato_flash > 0:
            return self.tomato_frames[min(4, len(self.tomato_frames) - 1)]
        idx = min(3, game_rules.HEALTH_MAX - self.health)
        return self.tomato_frames[min(idx, len(self.tomato_frames) - 1)]

    # -- button layout ---------------------------------------------------

    def layout_buttons(self) -> None:
        self.buttons = []

        if self.state == "SETTINGS":
            self._layout_settings_buttons()
            return
        if self.show_dictionary:
            self._layout_dictionary_buttons()
            return

        if self.paused:
            cont = pygame.Rect(0, 0, 260, 58)
            cont.center = (PAUSE_POPUP_RECT.centerx, PAUSE_POPUP_RECT.top + 150)
            leave = cont.copy()
            leave.center = (PAUSE_POPUP_RECT.centerx, PAUSE_POPUP_RECT.top + 230)
            self.buttons.append(Button(cont, "Continue", self._resume))
            self.buttons.append(Button(leave, "Exit Game", self._exit_level))
            return

        if self._can_pause():
            self.buttons.append(Button(PAUSE_BUTTON_RECT, "", self._pause, style="icon", icon="pause"))

        if self.state in ("LEVEL_COMPLETE", "LEVEL_FAILED", "INFINITE_RESULTS"):
            self.buttons.append(Button(pygame.Rect(1196, 18, 56, 56), "", self._open_dictionary,
                                       style="icon", icon="book"))
            self.buttons.append(Button(pygame.Rect(1126, 18, 56, 56), "", self._open_settings,
                                       style="icon", icon="gear"))

        if self.state == "MENU":
            self.buttons.append(Button(pygame.Rect(520, 300, 250, 40), "How to Play", self._open_how_to_play, style="link"))
            self.buttons.append(Button(pygame.Rect(520, 350, 250, 40), "Dictionary", self._open_dictionary, style="link"))
            self.buttons.append(Button(pygame.Rect(520, 400, 250, 40), "Settings", self._open_settings, style="link"))
            self.buttons.append(Button(pygame.Rect(510, 470, 260, 64), "Start", self._open_level_select))
        elif self.state == "HOW_TO_PLAY":
            self.buttons.append(Button(RETURN_BUTTON_RECT, "return", self._go_menu, style="icon", icon="return"))
        elif self.state == "LEVEL_SELECT":
            self.buttons.append(Button(RETURN_BUTTON_RECT, "return", self._go_menu, style="icon", icon="return"))
            self.buttons.append(Button(INFINITE_BUTTON_RECT, "Infinite Mode", self.start_infinite,
                                       enabled=self._infinite_available()))
            for level, rect in zip(sorted(game_data.LEVELS), LEVEL_CIRCLE_RECTS):
                unlocked = self._level_unlocked(level)
                action = (lambda lvl=level: self._select_level(lvl)) if unlocked else self._noop
                self.buttons.append(Button(rect, "", action, enabled=unlocked, style="hidden"))
        elif self.state == "TEACHING":
            for fid in self.teaching_ids:
                if fid in self.teaching_added:
                    continue
                _card, button_rect = self._add_card_layout(fid)
                self.buttons.append(
                    Button(button_rect, "Add To Your Dictionary", lambda fid=fid: self.on_add_to_dictionary(fid))
                )
        elif self.state == "FEEDBACK" and self.review_fallacy_id is not None:
            self.buttons.append(
                Button(pygame.Rect(0, 0, VIRTUAL_W, VIRTUAL_H), "", self._ack_review_card, style="hidden")
            )
        elif self.state in ("LEVEL_COMPLETE", "LEVEL_FAILED", "INFINITE_RESULTS"):
            home = pygame.Rect(0, 0, 88, 88)
            home.center = (560, 500)
            other = home.copy()
            other.center = (720, 500)
            self.buttons.append(Button(home, "home", self._go_home, style="icon", icon="home"))
            if self.state == "LEVEL_COMPLETE":
                self.buttons.append(Button(other, "next level", self._next_level, style="icon", icon="next"))
            elif self.state == "LEVEL_FAILED":
                self.buttons.append(Button(other, "try again", self._try_again, style="icon", icon="return"))
            else:
                self.buttons.append(Button(other, "play again", self._replay_infinite, style="icon", icon="return"))

    def _layout_dictionary_buttons(self) -> None:
        self.buttons.append(Button(RETURN_BUTTON_RECT, "return", self._close_dictionary,
                                   style="icon", icon="return"))
        if self.zoomed_card is not None:
            self.buttons.append(
                Button(pygame.Rect(0, 0, VIRTUAL_W, VIRTUAL_H), "", self._close_zoom, style="hidden")
            )
            return
        origin, left_rect, right_rect = self._book_geometry()
        turning = self.page_anim is not None
        if not turning:
            self._layout_card_buttons(left_rect, right_rect)
        if self._spread_count() <= 1:
            return
        left_half, right_half = self._half_rects(origin)
        self.buttons.append(
            Button(pygame.Rect(left_half.left - 80, left_half.centery - 36, 72, 72), "", self._prev_page,
                   enabled=not turning, style="icon", icon="prev")
        )
        self.buttons.append(
            Button(pygame.Rect(right_half.right + 8, right_half.centery - 36, 72, 72), "", self._next_page,
                   enabled=not turning, style="icon", icon="next")
        )
        self.buttons.append(Button(left_half, "", self._prev_page, enabled=not turning, style="hidden"))
        self.buttons.append(Button(right_half, "", self._next_page, enabled=not turning, style="hidden"))

    def _layout_card_buttons(self, left_rect: pygame.Rect, right_rect: pygame.Rect) -> None:
        ids = self._spread_ids(self.dictionary_page)
        slots = self._page_slots(left_rect) + self._page_slots(right_rect)
        for fid, slot in zip(ids, slots):
            if fid is None:
                continue
            hit = self._fitted_rect(self.dictionary_cards[fid], slot)
            self.buttons.append(Button(hit, "", lambda fid=fid: self._open_card(fid), style="hidden"))

    def _layout_settings_buttons(self) -> None:
        self.buttons.append(Button(RETURN_BUTTON_RECT, "return", self._close_settings,
                                   style="icon", icon="return"))
        for rect, action in zip(SETTINGS_ROW_RECTS, (self._toggle_music, self._toggle_sfx)):
            self.buttons.append(Button(rect, "", action, style="hidden"))
        if self.show_reset_confirm:
            self.buttons.append(Button(pygame.Rect(505, 530, 130, 46), "Yes, Reset", self._confirm_reset))
            self.buttons.append(Button(pygame.Rect(645, 530, 130, 46), "Cancel", self._cancel_reset))
        else:
            self.buttons.append(Button(pygame.Rect(530, 530, 220, 46), "Reset Progress", self._ask_reset))

    # -- button callbacks ---------------------------------------------------

    def _open_dictionary(self) -> None:
        self.show_dictionary = True
        self.dictionary_page = 0
        self.page_anim = None
        self.zoomed_card = None

    def _close_dictionary(self) -> None:
        self.show_dictionary = False
        self.page_anim = None
        self.zoomed_card = None

    def _open_card(self, fid: int) -> None:
        if self.page_anim is not None:
            return
        self.zoomed_card = fid
        self.zoom_t = 0.0

    def _close_zoom(self) -> None:
        self.zoomed_card = None

    def _dictionary_entries(self) -> list[int]:
        return sorted(self.progress.dictionary_ids)

    def _spread_starts(self) -> list[int]:
        """Each picture is a window of four cards, two on each page.

        Windows step forward, and the last one is pulled back so it is
        still four cards whenever that many have been collected.
        """
        count = len(self._dictionary_entries())
        if count == 0:
            return []
        if count <= CARDS_PER_SPREAD:
            return [0]
        last = count - CARDS_PER_SPREAD
        starts = list(range(0, last + 1, 2))
        if starts[-1] != last:
            starts.append(last)
        return starts

    def _spread_count(self) -> int:
        return len(self._spread_starts())

    def _turn_page(self, direction: int) -> None:
        if self.page_anim is not None or self.zoomed_card is not None:
            return
        spreads = self._spread_count()
        if spreads <= 1:
            return
        self.page_anim = {
            "t": 0.0,
            "direction": direction,
            "from": self.dictionary_page,
            "target": (self.dictionary_page + direction) % spreads,
        }

    def _prev_page(self) -> None:
        self._turn_page(-1)

    def _next_page(self) -> None:
        self._turn_page(1)

    def _open_settings(self) -> None:
        self.pre_settings_state = self.state
        self.show_reset_confirm = False
        self.state = "SETTINGS"

    def _close_settings(self) -> None:
        self.show_reset_confirm = False
        self.state = self.pre_settings_state

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
        self.start_infinite()

    def _try_again(self) -> None:
        self.start_level(self.level)

    def _go_home(self) -> None:
        self.state = "MENU"

    def _go_menu(self) -> None:
        self.state = "MENU"

    def _open_how_to_play(self) -> None:
        self.state = "HOW_TO_PLAY"

    def _open_level_select(self) -> None:
        self.state = "LEVEL_SELECT"

    def _level_unlocked(self, level: int) -> bool:
        """Levels open in order: each needs the previous one completed."""
        if level not in game_data.LEVELS:
            return False
        return level == 1 or (level - 1) in self.progress.completed_levels

    def _select_level(self, level: int) -> None:
        if self._level_unlocked(level):
            self.start_level(level)

    def _next_level(self) -> None:
        next_level = self.level + 1
        if self._level_unlocked(next_level):
            self.start_level(next_level)
        else:
            self.state = "LEVEL_SELECT"

    def _noop(self) -> None:
        pass

    # -- event handling ---------------------------------------------------

    def handle_click(self, pos: tuple[int, int]) -> None:
        for button in self.buttons:
            if button.enabled and button.rect.collidepoint(pos):
                button.action()
                return
        if not self.paused and not self.show_dictionary and self.state != "SETTINGS":
            self.handle_paper_click(pos)

    # -- drawing ---------------------------------------------------

    def draw(self, surf: pygame.Surface) -> None:
        if self.show_dictionary:
            surf.blit(self.bg, (0, 0))
            self._draw_dictionary(surf)
            self._draw_ui_buttons(surf)
            return

        faded_states = ("MENU", "HOW_TO_PLAY", "LEVEL_SELECT", "SETTINGS",
                        "LEVEL_COMPLETE", "LEVEL_FAILED", "INFINITE_RESULTS")
        surf.blit(self.bg_faded if self.state in faded_states else self.bg, (0, 0))
        if self.state in ("LEVEL_SELECT", "LEVEL_COMPLETE", "LEVEL_FAILED", "INFINITE_RESULTS"):
            surf.blit(self.logo_small, self.logo_small.get_rect(bottomright=(VIRTUAL_W - 24, VIRTUAL_H - 16)))

        if self.state == "MENU":
            self._draw_menu(surf)
        elif self.state == "HOW_TO_PLAY":
            self._draw_how_to_play(surf)
        elif self.state == "LEVEL_SELECT":
            self._draw_level_select(surf)
        elif self.state == "SETTINGS":
            self._draw_settings(surf)
        elif self.state == "TEACHING":
            self._draw_hud(surf)
            self._draw_teaching_cards(surf)
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

        if self.paused:
            self._draw_pause_popup(surf)

        self._draw_ui_buttons(surf)

    def _draw_ui_buttons(self, surf: pygame.Surface) -> None:
        for button in self.buttons:
            if button.style == "icon":
                font = self.fonts["body_bold"]
            elif button.style == "link":
                font = self.fonts["large"]
            elif button.label == "Start":
                font = self.fonts["title_bold"]
            else:
                font = self.fonts["body"]
            button.draw(surf, font)

    def _draw_hud(self, surf: pygame.Surface) -> None:
        health_frame = self.health_frames[
            min(len(self.health_frames) - 1, game_rules.HEALTH_MAX - self.health)
        ]
        surf.blit(health_frame, (92, 14))
        draw_outlined_text(surf, self.fonts["small"], "Tomato", (150, 84), width=2)

        if self.infinite:
            title = "Infinite Mode"
        else:
            title = f"Level {self.level}" + (" -- Warm-up" if self.phase == "WARMUP" else "")
            self._draw_opponent_bar(surf)
        draw_outlined_text(surf, self.fonts["large"], title, (VIRTUAL_W // 2, 34), width=3)

    def _draw_opponent_bar(self, surf: pygame.Surface) -> None:
        """Five pips, top right; they empty from the left as the enemy is hit."""
        pip_w, pip_h, gap = 40, 26, 6
        total = game_rules.OPPONENT_HEALTH_MAX
        right = VIRTUAL_W - 28
        left = right - total * pip_w - (total - 1) * gap
        for i in range(total):
            rect = pygame.Rect(left + i * (pip_w + gap), 24, pip_w, pip_h)
            full = i >= total - self.enemy_health
            pygame.draw.rect(surf, (60, 34, 20), rect.move(2, 3), border_radius=8)
            pygame.draw.rect(surf, INCORRECT_COLOR if full else (120, 100, 90), rect, border_radius=8)
            pygame.draw.rect(surf, (255, 240, 225), rect, 2, border_radius=8)
        draw_outlined_text(surf, self.fonts["small"], self.enemy_name, ((left + right) // 2, 70), width=2)

    def _draw_pause_popup(self, surf: pygame.Surface) -> None:
        dim = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        dim.fill((*OVERLAY_DARK, 170))
        surf.blit(dim, (0, 0))
        self._draw_white_card(surf, PAUSE_POPUP_RECT)
        label = self.fonts["title_bold"].render("PAUSED", True, BUTTON_BORDER)
        surf.blit(label, label.get_rect(center=(PAUSE_POPUP_RECT.centerx, PAUSE_POPUP_RECT.top + 62)))

    def _draw_menu(self, surf: pygame.Surface) -> None:
        paper = pygame.Rect(460, 90, 360, 490)
        draw_paper(surf, paper, tilt=-3)
        logo = pygame.transform.smoothscale(
            self.logo, (300, int(300 * self.logo.get_height() / self.logo.get_width()))
        )
        surf.blit(logo, logo.get_rect(midtop=(paper.centerx, 30)))
        tomato = pygame.transform.smoothscale(self.tomato_frames[0], (64, 64))
        surf.blit(tomato, tomato.get_rect(bottomright=(785, 482)))

    def _draw_how_to_play(self, surf: pygame.Surface) -> None:
        panel = pygame.Rect(240, 90, 800, 540)
        draw_paper(surf, panel, tilt=-1.5)
        title = self.fonts["title"].render("How to Play", True, TEXT_DARK)
        surf.blit(title, title.get_rect(center=(panel.centerx, panel.top + 50)))

        lines = [
            "Each level teaches three new fallacies. Add all three cards",
            "to your dictionary, then warm up -- warm-up misses cost nothing.",
            "",
            "In the official round, click the moving paper that names the",
            "fallacy in each claim before the ten-second timer runs out.",
            "",
            "Right answers hit your opponent; wrong answers and timeouts hit",
            "you. Neither side heals. Empty the opponent's bar to win.",
            "",
            "Beat a level to unlock Infinite Mode: endless review where right",
            "answers heal you and more papers appear as you go.",
        ]
        y = panel.top + 110
        for line in lines:
            if line:
                label = self.fonts["body"].render(line, True, (40, 34, 28))
                surf.blit(label, (panel.left + 50, y))
            y += self.fonts["body"].get_height() + 6

    def _draw_level_select(self, surf: pygame.Surface) -> None:
        if self._infinite_available():
            best = self.progress.infinite_best_seconds.get(INFINITE_SAVE_KEY, 0.0)
            hint = f"Best run: {best:.1f}s" if best else "Review everything you've unlocked"
        else:
            hint = "Complete a level to unlock"
        draw_outlined_text(surf, self.fonts["small"], hint,
                           (INFINITE_BUTTON_RECT.centerx, INFINITE_BUTTON_RECT.bottom + 18), width=2)

        for level, rect in zip(sorted(game_data.LEVELS), LEVEL_CIRCLE_RECTS):
            unlocked = self._level_unlocked(level)
            enemy = game_data.enemy_for_level(level)
            pygame.draw.circle(surf, (60, 34, 20), (rect.centerx + 3, rect.centery + 5), rect.width // 2)
            portrait = self.enemy_portraits[enemy] if unlocked else self.enemy_portraits_locked[enemy]
            surf.blit(portrait, rect)
            if not unlocked:
                draw_icon(surf, "lock", rect.center, 64, (245, 245, 245))
            label = f"LVL {level}" if unlocked else "LOCKED"
            draw_outlined_text(surf, self.fonts["large"], label, (rect.centerx, rect.bottom + 28), width=3)
            if level in self.progress.completed_levels:
                check_center = (rect.right - 18, rect.bottom - 20)
                draw_icon(surf, "check", (check_center[0] + 2, check_center[1] + 2), 36, (30, 70, 30))
                draw_icon(surf, "check", check_center, 36, (70, 190, 80))

    def _fitted_card(self, image: pygame.Surface, max_size: tuple[int, int], center: tuple[int, int]) -> pygame.Rect:
        fit = min(max_size[0] / image.get_width(), max_size[1] / image.get_height())
        rect = pygame.Rect(0, 0, max(1, round(image.get_width() * fit)), max(1, round(image.get_height() * fit)))
        rect.center = center
        return rect

    def _add_card_layout(self, fid: int) -> tuple[pygame.Rect, pygame.Rect]:
        """New cards sit side by side, each with its own add button underneath."""
        image = self.add_cards[fid]
        count = max(1, len(self.teaching_ids))
        index = self.teaching_ids.index(fid) if fid in self.teaching_ids else 0
        slot_w = (VIRTUAL_W - 40) // count
        center = (20 + slot_w * index + slot_w // 2, 360)
        card = self._fitted_card(image, (slot_w - 16, 380), center)
        button = pygame.Rect(0, 0, card.width - 40, 54)
        button.midtop = (card.centerx, card.bottom + 18)
        return card, button

    def _draw_teaching_cards(self, surf: pygame.Surface) -> None:
        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((*OVERLAY_DARK, 160))
        surf.blit(overlay, (0, 0))
        draw_outlined_text(surf, self.fonts["title_bold"], "New Fallacies!", (VIRTUAL_W // 2, 130), width=3)
        added = f"Add all three to start the warm-up  ({len(self.teaching_added)}/{len(self.teaching_ids)})"
        draw_outlined_text(surf, self.fonts["body"], added, (VIRTUAL_W // 2, 172), width=2)
        for fid in self.teaching_ids:
            image = self.add_cards.get(fid)
            if image is None:
                continue
            card, button = self._add_card_layout(fid)
            surf.blit(pygame.transform.smoothscale(image, card.size), card)
            if fid in self.teaching_added:
                pygame.draw.rect(surf, CORRECT_COLOR, button, border_radius=14)
                pygame.draw.rect(surf, (40, 100, 50), button, 3, border_radius=14)
                draw_icon(surf, "check", (button.centerx - 60, button.centery), 26, (255, 255, 255))
                added = self.fonts["body_bold"].render("Added", True, (255, 255, 255))
                surf.blit(added, added.get_rect(center=(button.centerx + 14, button.centery)))

    def _draw_gameplay(self, surf: pygame.Surface) -> None:
        self._draw_hud(surf)

        chef = self.chef_frames[0]
        surf.blit(chef, chef.get_rect(midbottom=CHEF_ANCHOR))

        self.tomato.draw(
            surf,
            self.health,
            TOMATO_ANCHOR,
            width=CHARACTER_SIZE,
            mistake=self.tomato_flash > 0,
            shake_time=FLASH_DURATION - self.tomato_flash,
            shake_duration=FLASH_DURATION,
        )

        self.enemies.get(self.enemy_name, self.peeler).draw(
            surf, self._enemy_frame_index(), ENEMY_ANCHOR,
            CHARACTER_SIZE,
            flip_x=True,
            damaged=self.enemy_flash > 0,
            shake_time=FLASH_DURATION - self.enemy_flash,
            shake_duration=FLASH_DURATION,
        )

        # The dialogue starts large in the center, then shrinks into the lower
        # speaker box where the enemy name (for example, "Peeler:") is shown.
        voice_box = pygame.Rect(160, 570, 960, 120)
        center_box = pygame.Rect(0, 0, 1080, 240)
        center_box.center = (VIRTUAL_W // 2, 300)

        if self.dialogue_phase == "CENTER":
            claim_box = center_box
        elif self.dialogue_phase == "MOVING":
            t = 1 - (self.dialogue_timer / DIALOGUE_MOVE_SECONDS)
            claim_box = lerp_rect(center_box, voice_box, t)
        else:
            claim_box = voice_box

        if self.state == "GAMEPLAY" and self.dialogue_phase == "DONE":
            bar_w = 300
            pct = 0 if self.timer_max <= 0 else max(0.0, self.timer / self.timer_max)
            bar_rect = pygame.Rect(0, 0, bar_w, 16)
            bar_rect.midtop = (VIRTUAL_W // 2, 70)
            pygame.draw.rect(surf, (90, 60, 40), bar_rect, border_radius=8)
            fill_rect = pygame.Rect(bar_rect.left, bar_rect.top, int(bar_w * pct), bar_rect.height)
            pygame.draw.rect(surf, (235, 190, 90), fill_rect, border_radius=8)
            pygame.draw.rect(surf, PANEL_BORDER, bar_rect, width=2, border_radius=8)

            if not self.paused:  # no free study time behind the pause menu
                for paper in self.papers:
                    paper.draw(surf, self.fonts["paper"])

        draw_panel(surf, claim_box, radius=16)
        speaker = self.fonts["body"].render(f"{self.enemy_name}:", True, PANEL_BORDER)
        surf.blit(speaker, (claim_box.left + 24, claim_box.top + 12))
        for i, line in enumerate(wrap_text(self.current_claim, self.fonts["body"], claim_box.width - 48)[:4]):
            label = self.fonts["body"].render(line, True, TEXT_DARK)
            surf.blit(label, (claim_box.left + 24, claim_box.top + 44 + i * 26))

        if self.state == "FEEDBACK":
            if self.review_fallacy_id is not None:
                self._draw_review_flashcard(surf)
            self._draw_feedback_banner(surf)

    def _draw_gameplay_frozen(self, surf: pygame.Surface) -> None:
        self.state, saved = "GAMEPLAY", self.state
        self.papers = []
        self._draw_gameplay(surf)
        self.state = saved

    def _draw_feedback_banner(self, surf: pygame.Surface) -> None:
        color = CORRECT_COLOR if self.result_correct else INCORRECT_COLOR
        image = self._banner_surface(self.result_label, color)
        if self.review_fallacy_id is not None:
            elapsed = self.review_age
            if elapsed < FEEDBACK_ENTER_SECONDS:
                t = elapsed / FEEDBACK_ENTER_SECONDS
                u = t - 1
                settle = 1 + 1.18 * u ** 3 + 0.18 * u ** 2
                x_offset = -image.get_width() + (image.get_width() - 24) * settle
            else:
                x_offset = -24
        else:
            total = game_rules.FEEDBACK_HOLD_SECONDS
            elapsed = max(0.0, total - self.feedback_timer)

            if elapsed < FEEDBACK_ENTER_SECONDS:
                t = elapsed / FEEDBACK_ENTER_SECONDS
                u = t - 1
                settle = 1 + 1.18 * u ** 3 + 0.18 * u ** 2
                x_offset = -image.get_width() + (image.get_width() - 24) * settle
            elif elapsed > total - FEEDBACK_EXIT_SECONDS:
                t = (elapsed - (total - FEEDBACK_EXIT_SECONDS)) / FEEDBACK_EXIT_SECONDS
                x_offset = -24 + (VIRTUAL_W + 24) * t ** 3
            else:
                x_offset = -24

        surf.blit(image, (round(x_offset), 150 - image.get_height() // 2))

    def _banner_surface(
        self, text: str, background: tuple[int, int, int]
    ) -> pygame.Surface:
        """Return a cached red or green result ribbon with its message."""
        key = (text, background)
        if key not in self.banner_cache:
            width, height = VIRTUAL_W + 48, 120
            image = pygame.Surface((width, height + 14), pygame.SRCALPHA)
            pygame.draw.polygon(
                image,
                (39, 12, 9, 100),
                [(0, 12), (width, height // 2 + 12), (width, height + 12), (0, height + 12)],
            )

            if background == CORRECT_COLOR:
                edge, highlight, shade, accent = (30, 96, 59), (134, 190, 145), (23, 77, 48), (78, 153, 104)
            else:
                edge, highlight, shade, accent = (164, 47, 42), (237, 141, 106), (121, 39, 31), (218, 101, 83)

            pygame.draw.polygon(
                image,
                edge,
                [(0, 0), (width, 0), (width - 20, height // 2), (width, height), (0, height), (20, height // 2)],
            )
            pygame.draw.rect(image, background, (20, 9, width - 40, height - 18))
            pygame.draw.line(image, highlight, (24, 12), (width - 24, 12), 2)
            pygame.draw.line(image, shade, (24, height - 10), (width - 24, height - 10), 3)
            for x in (75, 105, width - 125, width - 95):
                pygame.draw.polygon(
                    image,
                    accent,
                    [(x, 28), (x + 10, 28), (x - 14, height - 28), (x - 24, height - 28)],
                )

            label = self.banner_font.render(text, True, (255, 246, 229))
            image.blit(label, label.get_rect(center=(width // 2, height // 2)))
            self.banner_cache[key] = image
        return self.banner_cache[key]

    def _draw_gavel(self, surf: pygame.Surface) -> None:
        progress = 1 - max(0.0, self.gavel_timer) / GAVEL_DURATION
        frame_idx = min(len(self.chef_frames) - 1, int(progress * len(self.chef_frames)))
        chef = self.chef_frames[frame_idx]
        overlay = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        overlay.fill((20, 12, 8, 140))
        surf.blit(overlay, (0, 0))
        big = pygame.transform.smoothscale(chef, (chef.get_width() * 2, chef.get_height() * 2))
        surf.blit(big, big.get_rect(center=(VIRTUAL_W // 2, VIRTUAL_H // 2)))

    def _draw_white_card(self, surf: pygame.Surface, card: pygame.Rect) -> None:
        shadow = pygame.Surface(card.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 80), shadow.get_rect(), border_radius=18)
        surf.blit(shadow, card.move(6, 8))
        pygame.draw.rect(surf, CARD_WHITE, card, border_radius=18)
        for x in (card.left + 18, card.right - 18):
            for y in (card.top + 18, card.bottom - 18):
                pygame.draw.circle(surf, SPARKLE_COLOR, (x, y), 4)

    def _draw_result_card(self, surf: pygame.Surface, title: str, color: tuple) -> None:
        card = pygame.Rect(360, 120, 560, 380)
        self._draw_white_card(surf, card)
        label = self.fonts["title_bold"].render(title, True, color)
        surf.blit(label, label.get_rect(center=(card.centerx, card.top + 62)))

        tomato_idx = 0 if title == "LEVEL COMPLETE" else len(self.tomato_frames) - 1
        tomato_img = pygame.transform.smoothscale(self.tomato_frames[tomato_idx], (180, 180))
        surf.blit(tomato_img, tomato_img.get_rect(center=(card.centerx, card.top + 200)))

        if title == "LEVEL COMPLETE":
            sub = f"{self.enemy_name} is out of health!"
        else:
            sub = self.fail_reason or "Health depleted -- give it another go."
        sub_label = self.fonts["small"].render(sub, True, (90, 80, 70))
        surf.blit(sub_label, sub_label.get_rect(center=(card.centerx, card.top + 310)))

    def _draw_infinite_results(self, surf: pygame.Surface) -> None:
        card = pygame.Rect(360, 120, 560, 380)
        self._draw_white_card(surf, card)
        label = self.fonts["title_bold"].render("INFINITE MODE", True, BUTTON_BORDER)
        surf.blit(label, label.get_rect(center=(card.centerx, card.top + 62)))
        survived = self.fonts["title"].render(f"{self.infinite_survived:.1f}s", True, TEXT_DARK)
        surf.blit(survived, survived.get_rect(center=(card.centerx, card.top + 150)))
        best = self.progress.infinite_best_seconds.get(INFINITE_SAVE_KEY, 0.0)
        best_label = self.fonts["body"].render(f"Best: {best:.1f}s", True, TEXT_DARK)
        surf.blit(best_label, best_label.get_rect(center=(card.centerx, card.top + 210)))
        if self.infinite_is_best:
            new_best = self.fonts["body_bold"].render("New best!", True, CORRECT_COLOR)
            surf.blit(new_best, new_best.get_rect(center=(card.centerx, card.top + 250)))

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

    def _book_geometry(self) -> tuple[tuple[int, int], pygame.Rect, pygame.Rect]:
        bw, bh = self.book_image.get_size()
        origin = ((VIRTUAL_W - bw) // 2, (VIRTUAL_H - bh) // 2)
        scale_x = bw / BOOK_CROP.width
        scale_y = bh / BOOK_CROP.height

        def map_rect(src: pygame.Rect) -> pygame.Rect:
            return pygame.Rect(
                origin[0] + round((src.left - BOOK_CROP.left) * scale_x),
                origin[1] + round((src.top - BOOK_CROP.top) * scale_y),
                max(1, round(src.width * scale_x)),
                max(1, round(src.height * scale_y)),
            )

        return origin, map_rect(LEFT_PAGE_SRC), map_rect(RIGHT_PAGE_SRC)

    def _half_rects(self, origin: tuple[int, int]) -> tuple[pygame.Rect, pygame.Rect]:
        width, height = self.book_image.get_size()
        mid = width // 2
        gutter = self.page_gutter
        left = pygame.Rect(origin[0], origin[1], mid - gutter, height)
        right = pygame.Rect(origin[0] + mid + gutter, origin[1], width - mid - gutter, height)
        return left, right

    def _spread_ids(self, spread: int) -> tuple[int | None, ...]:
        """Four slots: left top, left bottom, right top, right bottom.

        Cards fill across the book first (left top, right top, then the
        bottoms) so each picture has two cards on each page.
        """
        entries = self._dictionary_entries()
        starts = self._spread_starts()
        if not starts:
            return (None, None, None, None)
        start = starts[spread % len(starts)]
        window = entries[start:start + CARDS_PER_SPREAD]
        placed: list[int | None] = [None, None, None, None]
        for offset, slot in enumerate((0, 2, 1, 3)):
            if offset < len(window):
                placed[slot] = window[offset]
        return tuple(placed)

    def _page_slots(self, page: pygame.Rect) -> tuple[pygame.Rect, pygame.Rect]:
        gap = max(6, page.height // 28)
        slot_h = (page.height - gap) // 2
        top = pygame.Rect(page.left, page.top, page.width, slot_h)
        bottom = pygame.Rect(page.left, top.bottom + gap, page.width, page.bottom - (top.bottom + gap))
        return top, bottom

    def _fitted_rect(self, image: pygame.Surface, slot: pygame.Rect) -> pygame.Rect:
        scale = min(slot.width / image.get_width(), slot.height / image.get_height())
        size = (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale)))
        rect = pygame.Rect(0, 0, size[0], size[1])
        rect.center = slot.center
        return rect

    def _blit_fitted(self, surf: pygame.Surface, image: pygame.Surface, slot: pygame.Rect) -> None:
        rect = self._fitted_rect(image, slot)
        surf.blit(pygame.transform.smoothscale(image, rect.size), rect)

    def _compose_page(self, card_ids: tuple[int | None, int | None], size: tuple[int, int]) -> pygame.Surface:
        key = ("page", card_ids, size)
        cached = self._card_cache.get(key)
        if cached is not None:
            return cached
        page = pygame.Surface(size, pygame.SRCALPHA)
        local = pygame.Rect(0, 0, size[0], size[1])
        for fid, slot in zip(card_ids, self._page_slots(local)):
            if fid is not None:
                self._blit_fitted(page, self.dictionary_cards[fid], slot)
        self._card_cache[key] = page
        return page

    def _turning_sheet(
        self,
        side: int,
        card_ids: tuple[int | None, int | None],
        half_rect: pygame.Rect,
        card_page: pygame.Rect,
    ) -> pygame.Surface:
        key = ("sheet", side, card_ids, half_rect.size)
        cached = self._card_cache.get(key)
        if cached is not None:
            return cached
        sheet = self.page_halves[side].copy()
        local_page = card_page.move(-half_rect.left, -half_rect.top)
        for fid, slot in zip(card_ids, self._page_slots(local_page)):
            if fid is not None:
                self._blit_fitted(sheet, self.dictionary_cards[fid], slot)
        self._card_cache[key] = sheet
        return sheet

    def _hinge_blit(
        self,
        surf: pygame.Surface,
        image: pygame.Surface,
        rect: pygame.Rect,
        scale: float,
        hinge: str,
    ) -> None:
        scale = max(0.0, min(1.0, scale))
        if scale <= 0.02:
            return
        new_w = max(1, int(rect.width * scale))
        scaled = pygame.transform.smoothscale(image, (new_w, rect.height))
        x = rect.left if hinge == "left" else rect.right - new_w
        surf.blit(scaled, (x, rect.top))
        shade = pygame.Surface((new_w, rect.height), pygame.SRCALPHA)
        shade.fill((48, 28, 12, int(110 * (1 - scale))))
        surf.blit(shade, (x, rect.top))

    def _draw_spread(self, surf: pygame.Surface, spread: int, left_rect: pygame.Rect, right_rect: pygame.Rect) -> None:
        ids = self._spread_ids(spread)
        surf.blit(self._compose_page(ids[0:2], left_rect.size), left_rect)
        surf.blit(self._compose_page(ids[2:4], right_rect.size), right_rect)

    def _draw_stitch(self, surf: pygame.Surface, origin: tuple[int, int]) -> None:
        mid = self.book_image.get_width() // 2
        surf.blit(self.book_stitch, (origin[0] + mid - self.page_gutter, origin[1]))

    def _draw_page_turn(self, surf: pygame.Surface, left_rect: pygame.Rect, right_rect: pygame.Rect) -> None:
        origin, _, _ = self._book_geometry()
        left_half, right_half = self._half_rects(origin)
        anim = self.page_anim
        t = max(0.0, min(1.0, anim["t"]))
        src_ids = self._spread_ids(anim["from"])
        dst_ids = self._spread_ids(anim["target"])
        src_left = self._turning_sheet(0, src_ids[0:2], left_half, left_rect)
        src_right = self._turning_sheet(1, src_ids[2:4], right_half, right_rect)
        dst_left = self._turning_sheet(0, dst_ids[0:2], left_half, left_rect)
        dst_right = self._turning_sheet(1, dst_ids[2:4], right_half, right_rect)
        if anim["direction"] > 0:
            surf.blit(self.page_halves[0], left_half)
            surf.blit(dst_right, right_half)
            self._draw_stitch(surf, origin)
            surf.blit(self._compose_page(src_ids[0:2], left_rect.size), left_rect)
            if t < 0.5:
                self._hinge_blit(surf, src_right, right_half, 1 - smoothstep(t / 0.5), "left")
            else:
                self._hinge_blit(surf, dst_left, left_half, smoothstep((t - 0.5) / 0.5), "right")
        else:
            surf.blit(dst_left, left_half)
            surf.blit(self.page_halves[1], right_half)
            self._draw_stitch(surf, origin)
            surf.blit(self._compose_page(src_ids[2:4], right_rect.size), right_rect)
            if t < 0.5:
                self._hinge_blit(surf, src_left, left_half, 1 - smoothstep(t / 0.5), "right")
            else:
                self._hinge_blit(surf, dst_right, right_half, smoothstep((t - 0.5) / 0.5), "left")

    def _draw_dictionary(self, surf: pygame.Surface) -> None:
        origin, left_rect, right_rect = self._book_geometry()
        turning = self.page_anim is not None
        if not turning:
            surf.blit(self.book_image, origin)

        entries = self._dictionary_entries()
        if not entries:
            empty = self.fonts["body"].render("No fallacies collected yet.", True, TEXT_DARK)
            surf.blit(empty, empty.get_rect(center=self.book_image.get_rect(topleft=origin).center))
            return

        spreads = self._spread_count()
        self.dictionary_page %= spreads
        if not turning:
            self._draw_spread(surf, self.dictionary_page, left_rect, right_rect)
            shown = self.dictionary_page
        else:
            self._draw_page_turn(surf, left_rect, right_rect)
            shown = self.page_anim["from"]

        shown_ids = [fid for fid in self._spread_ids(shown) if fid is not None]
        positions = [entries.index(fid) + 1 for fid in shown_ids]
        page_label = self.fonts["small"].render(
            f"{min(positions)}–{max(positions)} / {len(entries)}", True, TEXT_DARK
        )
        book_rect = self.book_image.get_rect(topleft=origin)
        surf.blit(page_label, page_label.get_rect(midbottom=(book_rect.centerx, book_rect.bottom - 42)))
        if self.zoomed_card is not None:
            self._draw_zoomed_card(surf)

    def _draw_zoomed_card(self, surf: pygame.Surface) -> None:
        image = self.detail_cards.get(self.zoomed_card)
        if image is None:
            return
        dim = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
        dim.fill((16, 10, 8, 150))
        surf.blit(dim, (0, 0))
        fit = min(980 / image.get_width(), 620 / image.get_height())
        scale = 0.72 + 0.28 * smoothstep(self.zoom_t)
        width = max(1, int(image.get_width() * fit * scale))
        height = max(1, int(image.get_height() * fit * scale))
        scaled = pygame.transform.smoothscale(image, (width, height))
        surf.blit(scaled, scaled.get_rect(center=(VIRTUAL_W // 2, VIRTUAL_H // 2)))

    def _draw_review_flashcard(self, surf: pygame.Surface) -> None:
        image = self.detail_cards.get(self.review_fallacy_id)
        if image is None:
            return
        if self.review_age < FEEDBACK_ENTER_SECONDS:
            scale = 0.6 + 0.24 * (self.review_age / FEEDBACK_ENTER_SECONDS)
        else:
            scale = 0.9

        dest = self._fitted_card(image, (900, 420), (VIRTUAL_W // 2, 510))
        dest = pygame.Rect(0, 0, max(1, int(dest.width * scale)), max(1, int(dest.height * scale)))
        dest.center = (VIRTUAL_W // 2, 450)
        scaled = pygame.transform.smoothscale(image, dest.size)
        shadow = pygame.Surface(scaled.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (20, 10, 6, 70), shadow.get_rect(), border_radius=18)
        surf.blit(shadow, dest.move(0, 8))
        surf.blit(scaled, dest)

    def _draw_settings(self, surf: pygame.Surface) -> None:
        paper = SETTINGS_PAPER_RECT
        draw_paper(surf, paper, tilt=2)

        tomato = pygame.transform.smoothscale(self.tomato_frames[0], (110, 110))
        surf.blit(tomato, tomato.get_rect(center=(paper.centerx, paper.top + 110)))
        title = self.fonts["large"].render("Settings", True, TEXT_DARK)
        surf.blit(title, title.get_rect(center=(paper.centerx, paper.top + 200)))

        rows = (("Background Music", self.audio.music_on), ("Sound Effects", self.audio.sfx_on))
        for rect, (text, on) in zip(SETTINGS_ROW_RECTS, rows):
            label = self.fonts["body"].render(text, True, (70, 55, 40))
            surf.blit(label, label.get_rect(midleft=(rect.left, rect.centery)))
            switch = pygame.Rect(0, 0, 64, 32)
            switch.midright = (rect.right, rect.centery)
            pygame.draw.rect(surf, CORRECT_COLOR if on else (170, 160, 150), switch, border_radius=16)
            knob_x = switch.right - 16 if on else switch.left + 16
            pygame.draw.circle(surf, (255, 255, 255), (knob_x, switch.centery), 12)
            pygame.draw.line(surf, (215, 200, 180), (rect.left, rect.bottom + 6), (rect.right, rect.bottom + 6), 1)

        if self.show_reset_confirm:
            for i, line in enumerate(("Erase all saved dictionary", "and progress?")):
                warn = self.fonts["small"].render(line, True, INCORRECT_COLOR)
                surf.blit(warn, warn.get_rect(center=(paper.centerx, 486 + i * 20)))


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
    mouse_press_handled = False
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
                mouse_press_handled = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                # Some window managers consume the first press while focusing
                # the game window. Handle the release if no press reached us.
                if not mouse_press_handled and not portrait:
                    vpos = window_to_virtual(event.pos, screen.get_size())
                    game.handle_click(vpos)
                    game.layout_buttons()
                mouse_press_handled = False

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
