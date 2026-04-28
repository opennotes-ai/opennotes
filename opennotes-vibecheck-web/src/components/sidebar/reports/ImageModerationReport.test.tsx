import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import ImageModerationReport from "./ImageModerationReport";

type ImageModerationMatch = components["schemas"]["ImageModerationMatch"];

function imageMatch(
  overrides: Partial<ImageModerationMatch> = {},
): ImageModerationMatch {
  return {
    utterance_id: "u-image",
    image_url: "https://cdn.example.test/image.jpg",
    adult: 0,
    violence: 0,
    racy: 0,
    medical: 0,
    spoof: 0,
    flagged: false,
    max_likelihood: 0,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("ImageModerationReport", () => {
  it("renders the empty fallback without a clear-images group when there are no matches", () => {
    render(() => <ImageModerationReport matches={[]} />);

    expect(screen.getByTestId("image-moderation-empty").textContent).toContain(
      "No image safety matches.",
    );
    expect(screen.queryByTestId("image-moderation-clear-group")).toBeNull();
    expect(screen.queryByTestId("image-moderation-flagged-list")).toBeNull();
  });

  it("renders all flagged images in the primary grid without a clear-images group", () => {
    render(() => (
      <ImageModerationReport
        matches={[
          imageMatch({
            utterance_id: "flagged-a",
            image_url: "https://cdn.example.test/flagged-a.jpg",
            flagged: true,
            adult: 0.91,
            max_likelihood: 0.91,
          }),
          imageMatch({
            utterance_id: "flagged-b",
            image_url: "https://cdn.example.test/flagged-b.jpg",
            flagged: true,
            violence: 0.82,
            max_likelihood: 0.82,
          }),
        ]}
      />
    ));

    expect(screen.getByTestId("image-moderation-flagged-list")).toBeDefined();
    expect(screen.queryByTestId("image-moderation-clear-group")).toBeNull();
    expect(screen.getAllByTestId("image-moderation-match")).toHaveLength(2);
    expect(screen.getByText("adult")).toBeDefined();
    expect(screen.getByText("violence")).toBeDefined();
  });

  it("renders all-clear image matches only inside a collapsed clear group", () => {
    render(() => (
      <ImageModerationReport
        matches={[
          imageMatch({
            utterance_id: "clear-a",
            image_url: "https://cdn.example.test/clear-a.jpg",
          }),
          imageMatch({
            utterance_id: "clear-b",
            image_url: "https://cdn.example.test/clear-b.jpg",
          }),
        ]}
      />
    ));

    const clearGroup = screen.getByTestId(
      "image-moderation-clear-group",
    ) as HTMLDetailsElement;
    expect(clearGroup.open).toBe(false);
    expect(clearGroup.textContent).toContain("2 clear images");
    expect(screen.queryByTestId("image-moderation-flagged-list")).toBeNull();
    expect(screen.getAllByTestId("image-moderation-match")).toHaveLength(2);
  });

  it("renders flagged images before the collapsed clear group when matches are mixed", () => {
    render(() => (
      <ImageModerationReport
        matches={[
          imageMatch({
            utterance_id: "flagged",
            image_url: "https://cdn.example.test/flagged.jpg",
            flagged: true,
            racy: 0.8,
            max_likelihood: 0.8,
          }),
          imageMatch({
            utterance_id: "clear",
            image_url: "https://cdn.example.test/clear.jpg",
          }),
        ]}
      />
    ));

    const flaggedList = screen.getByTestId("image-moderation-flagged-list");
    const clearGroup = screen.getByTestId("image-moderation-clear-group");
    expect(flaggedList.textContent).toContain("flagged");
    expect(clearGroup.textContent).toContain("1 clear image");
    expect(
      flaggedList.compareDocumentPosition(clearGroup) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows the all-clear SafeSearch status once for the clear group, not once per image", () => {
    render(() => (
      <ImageModerationReport
        matches={[
          imageMatch({
            utterance_id: "clear-a",
            image_url: "https://cdn.example.test/clear-a.jpg",
          }),
          imageMatch({
            utterance_id: "clear-b",
            image_url: "https://cdn.example.test/clear-b.jpg",
          }),
        ]}
      />
    ));

    const report = screen.getByTestId("report-safety__image_moderation");
    expect(
      within(report).getAllByText(
        "No SafeSearch categories crossed the threshold.",
      ),
    ).toHaveLength(1);
  });
});
