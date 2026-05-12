import { describe, expect, it } from "vitest";
import type { components } from "../../lib/generated-types";
import { utteranceLabel } from "./utteranceLabel";

type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

function anchor(utteranceId: string, position: number): UtteranceAnchor {
  return {
    utterance_id: utteranceId,
    position,
  };
}

describe("utteranceLabel", () => {
  it("labels posts by their position within multi-post sources", () => {
    const anchors = [
      anchor("post-0-aaa", 1),
      anchor("comment-1-bbb", 2),
      anchor("post-2-ccc", 3),
    ];

    expect(utteranceLabel("post-0-aaa", anchors)).toBe("post #1");
    expect(utteranceLabel("post-2-ccc", anchors)).toBe("post #2");
  });

  it("labels comments by their position within comment utterances", () => {
    const anchors = [
      anchor("post-0-aaa", 1),
      anchor("comment-1-bbb", 2),
      anchor("reply-2-ccc", 3),
      anchor("comment-3-ddd", 4),
      anchor("comment-4-eee", 5),
    ];

    expect(utteranceLabel("comment-4-eee", anchors)).toBe("comment #3");
  });

  it("labels replies by their position within reply utterances", () => {
    const anchors = [
      anchor("reply-0-aaa", 1),
      anchor("comment-1-bbb", 2),
      anchor("reply-2-ccc", 3),
    ];

    expect(utteranceLabel("reply-2-ccc", anchors)).toBe("reply #2");
  });

  it("labels the only post in a source as main post", () => {
    const anchors = [
      anchor("post-0-aaa", 1),
      anchor("comment-1-bbb", 2),
      anchor("comment-2-ccc", 3),
    ];

    expect(utteranceLabel("post-0-aaa", anchors)).toBe("main post");
  });

  it("falls back to item position for UUID-shaped ids", () => {
    const anchors = [
      anchor("post-0-aaa", 1),
      anchor("69499532-d5ca-4d60-917b-7d9b7606ec5a", 2),
      anchor("comment-2-bbb", 3),
    ];

    expect(
      utteranceLabel("69499532-d5ca-4d60-917b-7d9b7606ec5a", anchors),
    ).toBe("item #2");
  });

  it("falls back to item position for ids with unknown prefixes", () => {
    const anchors = [
      anchor("post-0-aaa", 1),
      anchor("quote-1-bbb", 2),
      anchor("comment-2-ccc", 3),
    ];

    expect(utteranceLabel("quote-1-bbb", anchors)).toBe("item #2");
  });

  it("uses an unknown item label when the id is absent from anchors", () => {
    expect(utteranceLabel("post-0-aaa", [])).toBe("item #?");
  });

  it("never exposes opaque legacy terms in labels", () => {
    const anchors = [
      anchor("post-0-aaa", 1),
      anchor("comment-1-bbb", 2),
      anchor("reply-2-ccc", 3),
      anchor("quote-3-ddd", 4),
    ];

    expect(utteranceLabel("post-0-aaa", anchors)).not.toMatch(
      /turn|utterance|post-0-aaa/i,
    );
    expect(utteranceLabel("comment-1-bbb", anchors)).not.toMatch(
      /turn|utterance|comment-1-bbb/i,
    );
    expect(utteranceLabel("reply-2-ccc", anchors)).not.toMatch(
      /turn|utterance|reply-2-ccc/i,
    );
    expect(utteranceLabel("quote-3-ddd", anchors)).not.toMatch(
      /turn|utterance|quote-3-ddd/i,
    );
  });
});
