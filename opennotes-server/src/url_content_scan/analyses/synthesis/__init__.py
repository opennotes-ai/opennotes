__all__ = [
    "HeadlineSummaryInputs",
    "OverallInputs",
    "WeatherInputs",
    "all_inputs_clear",
    "evaluate_overall",
    "evaluate_weather",
    "overall_recommendation_agent",
    "run_headline_summary",
    "weather_report_agent",
]

_HEADLINE = {"HeadlineSummaryInputs", "all_inputs_clear", "run_headline_summary"}
_WEATHER = {"WeatherInputs", "evaluate_weather", "weather_report_agent"}
_OVERALL = {"OverallInputs", "evaluate_overall", "overall_recommendation_agent"}


def __getattr__(name: str):
    if name in _HEADLINE:
        from src.url_content_scan.analyses.synthesis.headline_summary_agent import (  # noqa: PLC0415
            HeadlineSummaryInputs,
            all_inputs_clear,
            run_headline_summary,
        )

        return {
            "HeadlineSummaryInputs": HeadlineSummaryInputs,
            "all_inputs_clear": all_inputs_clear,
            "run_headline_summary": run_headline_summary,
        }[name]
    if name in _WEATHER:
        from src.url_content_scan.analyses.synthesis.weather_report_agent import (  # noqa: PLC0415
            WeatherInputs,
            evaluate_weather,
            weather_report_agent,
        )

        return {
            "WeatherInputs": WeatherInputs,
            "evaluate_weather": evaluate_weather,
            "weather_report_agent": weather_report_agent,
        }[name]
    if name in _OVERALL:
        from src.url_content_scan.analyses.synthesis.overall_recommendation_agent import (  # noqa: PLC0415
            OverallInputs,
            evaluate_overall,
            overall_recommendation_agent,
        )

        return {
            "OverallInputs": OverallInputs,
            "evaluate_overall": evaluate_overall,
            "overall_recommendation_agent": overall_recommendation_agent,
        }[name]
    raise AttributeError(name)
