"""Domain entities and value objects. Pure data: no I/O, no framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Prompt:
    """One daily question.

    `answers` runs roughly from most to least obvious. The first name in each tuple is the canonical display
    name; the rest are aliases. `golden` is the hidden deep-cut answer that earns a bonus. `decoys` are wrong
    answers mixed into the autocomplete list so it doesn't give the answers away.
    """

    id: str
    text: str
    hint: str
    golden: str
    answers: list[tuple[str, ...]] = field(default_factory=list)
    decoys: list[str] = field(default_factory=list)

    @property
    def canonical_answers(self) -> list[str]:
        return [names[0] for names in self.answers]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "hint": self.hint,
            "golden": self.golden,
            "answers": [list(names) for names in self.answers],
            "decoys": list(self.decoys),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Prompt:
        return cls(
            id=data["id"],
            text=data["text"],
            hint=data["hint"],
            golden=data["golden"],
            answers=[tuple(names) for names in data["answers"]],
            decoys=data.get("decoys", []),
        )


@dataclass(frozen=True)
class ScoredGuess:
    """What a stored guess resolved to."""

    answer: str | None
    points: int
    share: float
