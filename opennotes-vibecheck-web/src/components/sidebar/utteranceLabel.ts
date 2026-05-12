import type { components } from "../../lib/generated-types";

type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];
type KnownUtteranceKind = "post" | "comment" | "reply";

const KNOWN_KINDS = new Set<string>(["post", "comment", "reply"]);

function kindFromId(utteranceId: string): KnownUtteranceKind | null {
  const [kind] = utteranceId.split("-");
  return KNOWN_KINDS.has(kind) ? (kind as KnownUtteranceKind) : null;
}

function itemFallback(
  utteranceId: string,
  anchors: readonly UtteranceAnchor[],
): string {
  const index = anchors.findIndex(
    (anchor) => anchor.utterance_id === utteranceId,
  );
  if (index === -1) return "item #?";

  const position = anchors[index]?.position;
  return `item #${Number.isFinite(position) && position > 0 ? position : index + 1}`;
}

function chunkSuffix(
  chunkIdx?: number | null,
  chunkCount?: number | null,
): string {
  if (
    chunkIdx === undefined ||
    chunkIdx === null ||
    chunkCount === undefined ||
    chunkCount === null ||
    chunkCount <= 1
  ) {
    return "";
  }
  return ` §${chunkIdx + 1}`;
}

export function utteranceLabel(
  utteranceId: string,
  anchors: readonly UtteranceAnchor[],
  chunkIdx?: number | null,
  chunkCount?: number | null,
): string {
  const kind = kindFromId(utteranceId);
  if (!kind) {
    return `${itemFallback(utteranceId, anchors)}${chunkSuffix(
      chunkIdx,
      chunkCount,
    )}`;
  }

  const sameKindAnchors = anchors.filter(
    (anchor) => kindFromId(anchor.utterance_id) === kind,
  );
  const sameKindIndex = sameKindAnchors.findIndex(
    (anchor) => anchor.utterance_id === utteranceId,
  );

  if (sameKindIndex === -1) {
    return `${itemFallback(utteranceId, anchors)}${chunkSuffix(
      chunkIdx,
      chunkCount,
    )}`;
  }
  if (kind === "post" && sameKindAnchors.length === 1) {
    return `main post${chunkSuffix(chunkIdx, chunkCount)}`;
  }

  return `${kind} #${sameKindIndex + 1}${chunkSuffix(chunkIdx, chunkCount)}`;
}
