from __future__ import annotations

from ksusha_game.application.session import GameSession


class KsushaGame(GameSession):
    """Backward-compatible alias.

    New code should depend on `GameSession` from `ksusha_game.application.session`.
    """

    pass
