from enum import Enum


class WeatherAxisLiteralinsightfulOnTopicChattyDriftingOffTopicLabel(str, Enum):
    CHATTY = "chatty"
    DRIFTING = "drifting"
    INSIGHTFUL = "insightful"
    OFF_TOPIC = "off_topic"
    ON_TOPIC = "on_topic"

    def __str__(self) -> str:
        return str(self.value)
