"""
User Enrollment DataFrame Builder for MFCoreScorer integration.

Transforms participant IDs into the DataFrame format expected by
Community Notes MFCoreScorer.
"""

import pandas as pd

DEFAULT_MODELING_GROUP = 13


class UserEnrollmentBuilder:
    """
    Builder for converting participant IDs to Community Notes userEnrollment DataFrame.

    The Community Notes MFCoreScorer expects a DataFrame with participant enrollment info.
    Since we don't have complex enrollment data, this builder assigns all participants
    to a default modeling group.
    """

    def build(
        self,
        participant_ids: list[str],
        include_unassigned: bool = True,
    ) -> pd.DataFrame:
        """
        Build a user enrollment DataFrame from participant IDs.

        Args:
            participant_ids: List of participant ID strings (e.g., Discord user IDs)
            include_unassigned: If True, all users are included in the default modeling group.
                               This is the recommended setting for initial implementation.

        Returns:
            DataFrame with Community Notes user enrollment columns:
                - participantId: The participant identifier
                - modelingGroup: The modeling group assignment (defaults to 1)
        """
        if not participant_ids:
            return self._create_empty_dataframe()

        modeling_group = DEFAULT_MODELING_GROUP if include_unassigned else 0

        rows = [
            {
                "participantId": participant_id,
                "modelingGroup": modeling_group,
            }
            for participant_id in participant_ids
        ]

        return pd.DataFrame(rows)

    def _create_empty_dataframe(self) -> pd.DataFrame:
        """Create an empty DataFrame with the required columns."""
        columns = ["participantId", "modelingGroup"]
        return pd.DataFrame(columns=columns)
