from enum import Enum


class SectionSlug(str, Enum):
    FACTS_CLAIMS_DEDUP = "facts_claims__dedup"
    FACTS_CLAIMS_EVIDENCE = "facts_claims__evidence"
    FACTS_CLAIMS_KNOWN_MISINFO = "facts_claims__known_misinfo"
    FACTS_CLAIMS_PREMISES = "facts_claims__premises"
    OPINIONS_SENTIMENTS_HIGHLIGHTS = "opinions_sentiments__highlights"
    OPINIONS_SENTIMENTS_SENTIMENT = "opinions_sentiments__sentiment"
    OPINIONS_SENTIMENTS_SUBJECTIVE = "opinions_sentiments__subjective"
    OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS = "opinions_sentiments__trends_oppositions"
    SAFETY_IMAGE_MODERATION = "safety__image_moderation"
    SAFETY_MODERATION = "safety__moderation"
    SAFETY_VIDEO_MODERATION = "safety__video_moderation"
    SAFETY_WEB_RISK = "safety__web_risk"
    TONE_DYNAMICS_FLASHPOINT = "tone_dynamics__flashpoint"
    TONE_DYNAMICS_SCD = "tone_dynamics__scd"

    def __str__(self) -> str:
        return str(self.value)
