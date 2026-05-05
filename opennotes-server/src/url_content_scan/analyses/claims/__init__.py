__all__ = [
    "EmbeddingServiceKnownMisinfoAdapter",
    "ExtractedClaim",
    "extract_claims",
    "run_claims_dedup",
    "run_known_misinfo",
]


def __getattr__(name: str):
    if name in {"ExtractedClaim", "run_claims_dedup"}:
        from src.url_content_scan.analyses.claims.dedup import (  # noqa: PLC0415
            ExtractedClaim,
            run_claims_dedup,
        )

        return {"ExtractedClaim": ExtractedClaim, "run_claims_dedup": run_claims_dedup}[name]
    if name == "extract_claims":
        from src.url_content_scan.analyses.claims.extract import extract_claims  # noqa: PLC0415

        return extract_claims
    if name in {"EmbeddingServiceKnownMisinfoAdapter", "run_known_misinfo"}:
        from src.url_content_scan.analyses.claims.known_misinfo import (  # noqa: PLC0415
            EmbeddingServiceKnownMisinfoAdapter,
            run_known_misinfo,
        )

        return {
            "EmbeddingServiceKnownMisinfoAdapter": EmbeddingServiceKnownMisinfoAdapter,
            "run_known_misinfo": run_known_misinfo,
        }[name]
    raise AttributeError(name)
