__all__ = [
    "FrameBytes",
    "MentionedImage",
    "MentionedVideo",
    "SafetyRecommendationInputs",
    "VideoSamplingError",
    "run_image_moderation",
    "run_pre_enqueue_web_risk",
    "run_safety_moderation",
    "run_safety_recommendation",
    "run_video_moderation",
    "run_web_risk",
    "sample_video",
]


def __getattr__(name: str):
    if name in {"MentionedImage", "run_image_moderation"}:
        from src.url_content_scan.analyses.safety.image_moderation import (  # noqa: PLC0415
            MentionedImage,
            run_image_moderation,
        )

        return {"MentionedImage": MentionedImage, "run_image_moderation": run_image_moderation}[
            name
        ]
    if name == "run_safety_moderation":
        from src.url_content_scan.analyses.safety.moderation import (  # noqa: PLC0415
            run_safety_moderation,
        )

        return run_safety_moderation
    if name in {"SafetyRecommendationInputs", "run_safety_recommendation"}:
        from src.url_content_scan.analyses.safety.recommendation import (  # noqa: PLC0415
            SafetyRecommendationInputs,
            run_safety_recommendation,
        )

        return {
            "SafetyRecommendationInputs": SafetyRecommendationInputs,
            "run_safety_recommendation": run_safety_recommendation,
        }[name]
    if name in {"MentionedVideo", "run_video_moderation"}:
        from src.url_content_scan.analyses.safety.video_moderation import (  # noqa: PLC0415
            MentionedVideo,
            run_video_moderation,
        )

        return {"MentionedVideo": MentionedVideo, "run_video_moderation": run_video_moderation}[
            name
        ]
    if name in {"FrameBytes", "VideoSamplingError", "sample_video"}:
        from src.url_content_scan.analyses.safety.video_sampler import (  # noqa: PLC0415
            FrameBytes,
            VideoSamplingError,
            sample_video,
        )

        return {
            "FrameBytes": FrameBytes,
            "VideoSamplingError": VideoSamplingError,
            "sample_video": sample_video,
        }[name]
    if name in {"run_pre_enqueue_web_risk", "run_web_risk"}:
        from src.url_content_scan.analyses.safety.web_risk import (  # noqa: PLC0415
            run_pre_enqueue_web_risk,
            run_web_risk,
        )

        return {
            "run_pre_enqueue_web_risk": run_pre_enqueue_web_risk,
            "run_web_risk": run_web_risk,
        }[name]
    raise AttributeError(name)
