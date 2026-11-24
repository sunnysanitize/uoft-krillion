"""Game constants: the knobs that define how UofT Krillion plays."""

from datetime import date
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")
LAUNCH_DATE = date(2026, 11, 1)

PROMPTS_PER_DAY = 7
TIME_LIMIT_SECONDS = 25
# Points per rarity tier. The one hidden "One in a Krillion" answer per prompt scores a flat 100.
TIER_POINTS = {"Common": 10, "Uncommon": 30, "Rare": 60, "Deep Cut": 85}
GOLDEN = "One in a Krillion"
GOLDEN_POINTS = 100
METERS_PER_POINT = 10

# Depth zones, shallowest first: (starting depth in meters, name).
ZONES = [
    (0, "Philosopher's Walk Shallows"),
    (1000, "Sid Smith Drop-off"),
    (2500, "Bahen Trench"),
    (4000, "Robarts Abyss"),
    (6000, "The Steam Tunnels"),
]

LEADERBOARD_SIZE = 15
