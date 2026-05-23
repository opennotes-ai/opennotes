"""Viafoura Tier 2 /interact action builder."""

from __future__ import annotations

from typing import Any

from .detector import ViafouraSignal


def build_viafoura_actions(signal: ViafouraSignal) -> list[dict[str, Any]]:
    """Build best-effort public Viafoura widget interaction actions."""
    return [
        {"type": "wait", "milliseconds": 2000},
        {"type": "scroll", "direction": "down"},
        {"type": "wait", "milliseconds": 1500},
        {
            "type": "executeJavascript",
            "script": """
                (async () => {
                    const sleep = (milliseconds) => new Promise((resolve) => {
                        setTimeout(resolve, milliseconds);
                    });
                    const normalizeText = (value) => (value || "").replace(/\\s+/g, " ").trim();
                    const markerSelector = "[data-platform-comments][data-platform='viafoura']";
                    const statusPrefix = "viafoura_status:";
                    const rootSelectors = [
                        "vf-widget#vf-conversations",
                        "[data-testid='vf-conversations-root']",
                        "[data-test='vf-conversations-root-element']",
                        ".vf3-comments",
                        "#vf-conversations",
                        "vf-conversations",
                        "#ap-comments",
                    ];
                    const expandSelectors = [
                        "[data-testid='vf-conversations-load-more-button']",
                        ".vf-threaded-content-indicator",
                        "button[data-testid='vf-conversations-reply-button']",
                        "button[aria-label*='more' i]",
                    ];
                    const commentContainerSelectors = [
                        "[data-testid='vf-comment']",
                        ".vf-comment",
                        "article",
                    ];
                    const commentTextFallbackSelectors = [
                        ".vf-comment__content-editor",
                        ".vf-content-text",
                    ];
                    const isBoilerplateText = (text) => (
                        !text
                        || /^All Comments?,?\\s*\\d*\\s*items?$/i.test(text)
                        || /Log in to comment/i.test(text)
                        || /^loading/i.test(text)
                    );
                    const findRoot = () => {
                        for (const selector of rootSelectors) {
                            const node = document.querySelector(selector);
                            if (node?.shadowRoot) {
                                return {root: node.shadowRoot, status: null};
                            }
                            if (node) {
                                return {root: node, status: null};
                            }
                        }
                        return {root: null, status: "host_missing"};
                    };
                    const appendStatusMarker = (status, comments = []) => {
                        document.querySelector(markerSelector)?.remove();
                        const marker = document.createElement("section");
                        marker.setAttribute("data-platform-comments", "true");
                        marker.setAttribute("data-platform", "viafoura");
                        marker.setAttribute("data-platform-status", status);
                        marker.setAttribute("aria-label", "Comments");
                        const heading = document.createElement("h2");
                        heading.textContent = "Comments";
                        marker.appendChild(heading);
                        for (const comment of comments) {
                            const item = document.createElement("article");
                            item.className = "comment";
                            const header = document.createElement("header");
                            header.textContent = comment.author;
                            const paragraph = document.createElement("p");
                            paragraph.textContent = comment.text;
                            item.appendChild(header);
                            item.appendChild(paragraph);
                            marker.appendChild(item);
                        }
                        (document.querySelector("article") || document.body).appendChild(marker);
                        return `${statusPrefix}${status};comments=${comments.length}`;
                    };
                    const collectComments = (root) => {
                        const comments = [];
                        let nodes = Array.from(root.querySelectorAll?.(commentContainerSelectors.join(",")) || []);
                        if (nodes.length === 0) {
                            nodes = Array.from(root.querySelectorAll?.(commentTextFallbackSelectors.join(",")) || []);
                        }
                        for (const node of nodes) {
                            const text = normalizeText(node.textContent);
                            if (isBoilerplateText(text)) {
                                continue;
                            }
                            const commentRoot = node.closest?.("[data-testid='vf-comment'],.vf-comment") || node;
                            const authorNode = commentRoot
                                ?.querySelector?.("[data-testid*='author'],.vf-username,.vf-author");
                            const author = normalizeText(authorNode?.textContent) || "anonymous";
                            comments.push({author, text});
                        }
                        return comments;
                    };
                    const statusName = (status) => status.split(":", 2)[1]?.split(";", 1)[0] || "";
                    const clickExpansions = () => {
                        let clicked = false;
                        for (const selector of expandSelectors) {
                            for (const button of Array.from(document.querySelectorAll?.(selector) || [])) {
                                if (typeof button.click === "function") {
                                    button.click();
                                    clicked = true;
                                }
                            }
                        }
                        return clicked;
                    };

                    clickExpansions();
                    for (let attempt = 0; attempt < 20; attempt += 1) {
                        const {root, status} = findRoot();
                        if (!root) {
                            if (status === "host_missing") {
                                await sleep(500);
                                continue;
                            }
                            return appendStatusMarker(status || "host_missing");
                        }
                        const comments = collectComments(root);
                        if (comments.length > 0) {
                            return appendStatusMarker("copied", comments);
                        }
                        if (attempt === 4) {
                            clickExpansions();
                        }
                        await sleep(500);
                    }
                    const {root, status} = findRoot();
                    if (!root) {
                        return appendStatusMarker(status || "timeout");
                    }
                    return appendStatusMarker(normalizeText(root.textContent) ? "shell_only" : "timeout");
                })();
            """,
        },
        {"type": "wait", "milliseconds": 1000},
    ]


__all__ = ["build_viafoura_actions"]
