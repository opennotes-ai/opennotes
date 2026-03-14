from typing import Any


class PreloadedDataProvider:
    def __init__(
        self,
        ratings: list[dict[str, Any]],
        notes: list[dict[str, Any]],
        participants: list[str],
    ) -> None:
        self._ratings = ratings
        self._notes = notes
        self._participants = participants

    def get_all_ratings(self, _community_id: str) -> list[dict[str, Any]]:
        return self._ratings

    def get_all_notes(self, _community_id: str) -> list[dict[str, Any]]:
        return self._notes

    def get_all_participants(self, _community_id: str) -> list[str]:
        return self._participants
