from typing import Protocol, runtime_checkable

import pyarrow as pa


@runtime_checkable
class CommunityDataProvider(Protocol):
    def get_all_ratings(self, community_id: str) -> pa.Table: ...

    def get_all_notes(self, community_id: str) -> pa.Table: ...

    def get_all_participants(self, community_id: str) -> pa.Array: ...
