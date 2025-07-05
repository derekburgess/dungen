from dataclasses import dataclass, field
from typing import List


@dataclass
class Player:
    name: str
    age: int
    gender: str
    race: str
    role: str
    alignment: str
    health: int
    stamina: int
    inventory: List[str] = field(default_factory=list)


@dataclass
class EncounterEntry:
    turn: int
    npc: str
    npc_health: int
    damage: int
    dialog: str