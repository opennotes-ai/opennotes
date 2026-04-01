import { Page } from "@playwright/test";

export class CommunityReviewPage {
  constructor(private page: Page) {}

  async goToReviews(): Promise<void> {
    await this.page.goto("/community-reviews");
  }

  async waitForLoad(): Promise<void> {
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForSelector(".opennotes-review-panel", { state: "visible" });
    await this.page.waitForSelector(".opennotes-review-panel__loading", { state: "detached" });
  }

  async getReviewItems(): Promise<{ noteId: string; actionType: string }[]> {
    const items = await this.page.locator(".opennotes-review-panel__item").all();
    const results: { noteId: string; actionType: string }[] = [];

    for (const item of items) {
      const reasonEl = item.locator(".opennotes-review-panel__item-reason");
      const voteWidget = item.locator(".opennotes-vote-widget");

      const actionType = (await reasonEl.getAttribute("data-reason")) ??
        (await reasonEl.textContent()) ?? "";
      const noteId = (await voteWidget.getAttribute("data-note-id")) ?? "";

      results.push({ noteId: noteId.trim(), actionType: actionType.trim() });
    }

    return results;
  }

  async getItemCount(): Promise<number> {
    return this.page.locator(".opennotes-review-panel__item").count();
  }

  async voteHelpful(noteId: string): Promise<void> {
    const item = this.page.locator(`.opennotes-review-panel__item`).filter({
      has: this.page.locator(`.opennotes-vote-widget[data-note-id="${noteId}"]`),
    });
    await item.locator(".opennotes-vote-widget__btn--helpful").click();
    await this.page.waitForLoadState("networkidle");
  }

  async voteNotHelpful(noteId: string): Promise<void> {
    const item = this.page.locator(`.opennotes-review-panel__item`).filter({
      has: this.page.locator(`.opennotes-vote-widget[data-note-id="${noteId}"]`),
    });
    await item.locator(".opennotes-vote-widget__btn--not-helpful").click();
    await this.page.waitForLoadState("networkidle");
  }

  async isVoteWidgetVisible(): Promise<boolean> {
    const count = await this.page.locator(".opennotes-vote-widget").count();
    return count > 0;
  }

  async getVoteState(noteId: string): Promise<"voted" | "available" | "hidden"> {
    const selector = noteId
      ? `.opennotes-review-panel__item:has(.opennotes-vote-widget) .opennotes-vote-widget`
      : ".opennotes-vote-widget";

    const votedEl = this.page.locator(".opennotes-vote-widget__voted").first();
    const isVoted = await votedEl.isVisible().catch(() => false);
    if (isVoted) {
      return "voted";
    }

    const helpfulBtn = this.page.locator(".opennotes-vote-widget__btn--helpful").first();
    const isAvailable = await helpfulBtn.isVisible().catch(() => false);
    if (isAvailable) {
      return "available";
    }

    return "hidden";
  }

  async hasErrorMessage(): Promise<boolean> {
    const errorEl = this.page.locator(".opennotes-review-panel__error, .alert-error");
    return errorEl.isVisible().catch(() => false);
  }

  async getErrorText(): Promise<string> {
    const errorEl = this.page.locator(".opennotes-review-panel__error, .alert-error").first();
    return (await errorEl.textContent()) ?? "";
  }
}
