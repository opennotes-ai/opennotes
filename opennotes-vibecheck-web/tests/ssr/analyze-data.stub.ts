const getArchiveProbe = Object.assign(
  async () => ({
    ok: true,
    has_archive: false,
    archived_preview_url: null,
    can_iframe: true,
    blocking_header: null,
    csp_frame_ancestors: null,
  }),
  {
    key: "vibecheck-archive-probe",
    keyFor: (url: string, jobId?: string) =>
      `vibecheck-archive-probe:${url}:${jobId ?? ""}`,
  },
);

const getJobState = Object.assign(async () => null, {
  key: "vibecheck-job-state",
  keyFor: (jobId: string) => `vibecheck-job-state:${jobId}`,
});

const getScreenshot = Object.assign(async () => null, {
  key: "vibecheck-screenshot",
  keyFor: (url: string) => `vibecheck-screenshot:${url}`,
});

export { getArchiveProbe, getJobState, getScreenshot };
