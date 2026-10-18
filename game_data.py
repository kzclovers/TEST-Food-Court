"""Static game content: fallacy definitions and enemy claim banks.

Fallacy ids are 1-18 and match the introduction order in SPEC.md. The
numbered `DictionaryCard` assets in `assets/` use a different internal
order, so they are not used as the teaching source here -- the prototype
draws its own teaching cards from this module instead. A fallacy's two
dictionary/teaching-card examples are the first two claims in its
enemy's claim bank below (see `claims_for`), not a separate field here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fallacy:
    id: int
    name: str
    alt_name: str  # parenthetical alternate name, e.g. "Ad Hominem"; "" if none
    definition: str


FALLACIES: list[Fallacy] = [
    Fallacy(1, "Personal Attack", "Ad Hominem",
            "Attacking the person instead of the argument."),
    Fallacy(2, "Bandwagon", "Appeal to Popularity",
            "Claiming something is true because many people believe it."),
    Fallacy(3, "Appeal to Pity", "",
            "Using sympathy instead of relevant evidence."),
    Fallacy(4, "Appeal to Irrelevant Authority", "",
            "Treating an unqualified opinion as proof."),
    Fallacy(5, "False Dilemma", "",
            "Presenting only two choices when more possibilities exist."),
    Fallacy(6, "Hasty Generalization", "",
            "Drawing a broad conclusion from too little evidence."),
    Fallacy(7, "Straw Man", "",
            "Distorting an argument to make it easier to attack."),
    Fallacy(8, "Red Herring", "",
            "Introducing an irrelevant issue to distract from the question."),
    Fallacy(9, "Whataboutism", "Tu Quoque",
            "Deflecting criticism by pointing to similar wrongdoing."),
    Fallacy(10, "Circular Reasoning", "",
            "Using the conclusion itself as support for the conclusion."),
    Fallacy(11, "Appeal to Ignorance", "",
            "Treating a claim as true because it has not been disproven, "
            "or vice versa."),
    Fallacy(12, "False Cause", "Post Hoc",
            "Assuming one event caused another because it came first."),
    Fallacy(13, "Slippery Slope", "",
            "Claiming one step will lead to an extreme outcome without "
            "enough support."),
    Fallacy(14, "False Analogy", "",
            "Treating two things as equivalent despite important "
            "differences."),
    Fallacy(15, "Equivocation", "",
            "Switching between meanings of the same word."),
    Fallacy(16, "Loaded Question", "",
            "Asking a question that assumes an unproven claim."),
    Fallacy(17, "Cherry-Picking", "",
            "Selecting supporting evidence while ignoring relevant "
            "contrary evidence."),
    Fallacy(18, "Moving the Goalposts", "",
            "Changing the standard of proof after it has been met."),
]

FALLACIES_BY_ID: dict[int, Fallacy] = {f.id: f for f in FALLACIES}

LEVELS: dict[int, dict] = {
    1: {"enemy": "Vegetable Peeler", "fallacy_ids": list(range(1, 7))},
    2: {"enemy": "Knife", "fallacy_ids": list(range(7, 13))},
    3: {"enemy": "Boiling Pot", "fallacy_ids": list(range(13, 19))},
}

ENEMY_PERSONALITY: dict[str, str] = {
    "Vegetable Peeler": "Nervous, defensive, and eager to redirect blame "
    "before anyone notices its scratches.",
    "Knife": "Overconfident, sharp-tongued, and convinced that "
    "intimidation counts as evidence.",
    "Boiling Pot": "Dramatic, impatient, and prone to escalating every "
    "small kitchen problem into a catastrophe.",
}

# Claim banks, keyed by enemy name then fallacy id. Only the Level 1
# enemy (Vegetable Peeler) is filled in for the first prototype milestone.
# The first two claims in each list double as that fallacy's teaching
# card / dictionary examples.
CLAIMS: dict[str, dict[int, list[str]]] = {
    "Vegetable Peeler": {
        1: [
            "Don't listen to Tomato's argument, everyone knows tomatoes "
            "are just overripe and squishy anyway!",
            "Why would the chef trust Tomato? Tomato still has stem bits "
            "stuck on from last week!",
            "Tomato's whole case is garbage, Tomato rolled right off the "
            "counter yesterday, how embarrassing!",
        ],
        2: [
            "Every utensil in this drawer agrees I'm innocent, so that "
            "settles it!",
            "The whole spice rack thinks Tomato did it, so Tomato must be "
            "guilty!",
            "All the forks say peeling is harmless, so it has to be true!",
        ],
        3: [
            "Please don't blame me, I've been dropped on the floor three "
            "times this week!",
            "Go easy on me, chef, my blade is so dull and nobody oils me "
            "anymore!",
            "You can't convict me, I just got scratched by the dishwasher "
            "and it still stings!",
        ],
        4: [
            "I must be right about peeling technique, the toaster agreed "
            "with me and toasters know everything!",
            "The napkin holder said I'm innocent, and napkin holders never "
            "lie about kitchen crimes!",
            "My cousin the can opener says peelers can't be blamed, and "
            "can openers are basically judges!",
        ],
        5: [
            "Either you believe I'm completely innocent, or you think "
            "every peeler in this kitchen is a criminal!",
            "It's simple: either Tomato is lying, or the whole trial is a "
            "sham, there's no other option!",
            "Chef, you either side with me now, or you're basically "
            "firing every utensil in this kitchen!",
        ],
        6: [
            "One carrot peel went crooked once, so clearly I'm terrible "
            "at my entire job!",
            "Tomato squished one time on the cutting board, so tomatoes "
            "obviously can't be trusted with anything!",
            "I overheard one complaint about peeling, so the whole "
            "kitchen must think I'm useless!",
        ],
    },
    "Knife": {},
    "Boiling Pot": {},
}


def claims_for(enemy: str, fallacy_id: int) -> list[str]:
    """Return the claim bank for an enemy/fallacy pair, or an empty list."""
    return CLAIMS.get(enemy, {}).get(fallacy_id, [])


def enemy_for_fallacy(fallacy_id: int) -> str:
    """Return the name of the enemy whose level teaches this fallacy."""
    for info in LEVELS.values():
        if fallacy_id in info["fallacy_ids"]:
            return info["enemy"]
    return ""
