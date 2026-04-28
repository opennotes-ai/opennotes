export interface ScrollState {
  lastHighlightedId: string | null;
}

const STYLE_ATTR = "data-vibecheck-utterance-style";
const FLASH_ATTR = "data-vibecheck-flash";
const RING_ATTR = "data-vibecheck-ring";

function contentDocumentFor(
  iframeRef: HTMLIFrameElement | undefined,
): Document | null {
  if (!iframeRef) return null;
  try {
    return iframeRef.contentDocument;
  } catch {
    return null;
  }
}

function findUtterance(doc: Document, utteranceId: string): HTMLElement | null {
  for (const target of doc.querySelectorAll("[data-utterance-id]")) {
    if (target.getAttribute("data-utterance-id") === utteranceId) {
      return target as HTMLElement;
    }
  }
  return null;
}

export function ensureHighlightStyles(iframeDoc: Document): void {
  if (iframeDoc.head.querySelector(`style[${STYLE_ATTR}]`)) return;
  const style = iframeDoc.createElement("style");
  style.setAttribute(STYLE_ATTR, "");
  style.textContent = `
@keyframes vibecheck-utterance-flash {
  0% { background-color: var(--flash-color, rgba(255, 224, 0, 0.6)); }
  100% { background-color: transparent; }
}
[${FLASH_ATTR}] {
  animation: vibecheck-utterance-flash 1s ease-out 1;
}
[${RING_ATTR}] {
  outline: 2px solid var(--ring-color, rgba(255, 165, 0, 0.7));
  outline-offset: 2px;
  border-radius: 2px;
}
`;
  iframeDoc.head.append(style);
}

export function clearHighlight(
  iframeRef: HTMLIFrameElement | undefined,
  state: ScrollState,
): void {
  const iframeDoc = contentDocumentFor(iframeRef);
  if (iframeDoc && state.lastHighlightedId) {
    findUtterance(iframeDoc, state.lastHighlightedId)?.removeAttribute(RING_ATTR);
  }
  state.lastHighlightedId = null;
}

export function scrollToUtterance(
  iframeRef: HTMLIFrameElement | undefined,
  utteranceId: string,
  state: ScrollState,
): boolean {
  const iframeDoc = contentDocumentFor(iframeRef);
  if (!iframeDoc) return false;

  ensureHighlightStyles(iframeDoc);
  const target = findUtterance(iframeDoc, utteranceId);
  if (!target) {
    console.debug(`vibecheck utterance target not found: ${utteranceId}`);
    return false;
  }

  if (state.lastHighlightedId && state.lastHighlightedId !== utteranceId) {
    findUtterance(iframeDoc, state.lastHighlightedId)?.removeAttribute(RING_ATTR);
  }

  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.setAttribute(FLASH_ATTR, "");
  requestAnimationFrame(() => {
    target.setAttribute(RING_ATTR, "");
  });
  setTimeout(() => {
    target.removeAttribute(FLASH_ATTR);
  }, 1100);
  state.lastHighlightedId = utteranceId;
  return true;
}
