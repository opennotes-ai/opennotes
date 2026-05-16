__all__ = [
    "HeadlineSummaryInputs",
    "all_inputs_clear",
    "run_headline_summary",
]


def __getattr__(name: str):
    if name in {"HeadlineSummaryInputs", "all_inputs_clear", "run_headline_summary"}:
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
    raise AttributeError(name)
