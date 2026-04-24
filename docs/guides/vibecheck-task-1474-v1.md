# TASK-1474 V-1 Verification

Post-deploy checklist for the Vibecheck Web Risk, GCP moderation, Vision, and Fact Check rollout.

## Browser Flow

1. Open `https://vibecheck.opennotes.ai`.
2. Submit a safe URL that includes page text, images, and an embedded YouTube URL.
3. Confirm the sidebar shows all 10 sections and the four Safety sections complete:
   - Moderation
   - Web Risk
   - Images
   - Videos
4. Confirm the Moderation section shows separate OpenAI moderation and Google Natural Language groups when both providers return matches.
5. Submit a Web Risk test URL and confirm the page renders the `unsafe_url` failure card with threat chips and no sidebar.

## Observability

In Logfire, confirm spans are present for:

- `vibecheck.external_api` with `api=webrisk`
- `vibecheck.external_api` with `api=gcp_nl`
- `vibecheck.external_api` with `api=vision`
- `vibecheck.external_api` with `api=factcheck`
- `vibecheck.video_sampler`

In Grafana or Prometheus, confirm the new metrics have samples for all deployed providers:

- `vibecheck_external_api_calls_total{api=...}`
- `vibecheck_external_api_latency_seconds{api=...}`
- `vibecheck_external_api_errors_total{api=...}` when forced failures occur
- `vibecheck_external_api_flagged_total{api=...}` when flagged fixtures return matches
- `vibecheck_section_media_dropped_total{media_type=...}` when fixture pages exceed image or video caps

Record the deployment SHA, fixture URLs, dashboard links, and timestamp in the task notes when complete.
