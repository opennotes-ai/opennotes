from enum import Enum


class WeatherAxisAlternativeLiteralsourcedFactualClaimsFirstPersonHearsayMisleadingLabel(
    str, Enum
):
    FACTUAL_CLAIMS = "factual_claims"
    FIRST_PERSON = "first_person"
    HEARSAY = "hearsay"
    MISLEADING = "misleading"
    SOURCED = "sourced"

    def __str__(self) -> str:
        return str(self.value)
