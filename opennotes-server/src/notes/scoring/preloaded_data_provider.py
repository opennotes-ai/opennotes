import pyarrow as pa


class PreloadedDataProvider:
    def __init__(
        self,
        ratings: pa.Table,
        notes: pa.Table,
        participants: pa.Array,
    ) -> None:
        self._ratings = ratings
        self._notes = notes
        self._participants = participants

    def get_all_ratings(self, community_id: str) -> pa.Table:
        return self._ratings

    def get_all_notes(self, community_id: str) -> pa.Table:
        return self._notes

    def get_all_participants(self, community_id: str) -> pa.Array:
        return self._participants
