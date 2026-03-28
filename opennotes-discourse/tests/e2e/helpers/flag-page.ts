import { Page } from "playwright";

export class FlagPage {
  constructor(private page: Page) {}

  async flagPost(postIndex: number, reason?: string): Promise<void> {
    const posts = this.page.locator(".topic-post");
    const post = posts.nth(postIndex);

    await post.hover();

    const moreButton = post.locator(".post-controls .show-more-actions");
    if (await moreButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await moreButton.click();
    }

    const flagButton = post.locator(".post-controls .flag-post, .post-controls button[title='flag this post']");
    await flagButton.click();

    await this.page.waitForSelector(".flag-modal, .modal-body .flagging-topic", {
      state: "visible",
    });

    if (reason) {
      const radioLabel = this.page.locator(".flag-modal .radio-label, .modal-body label").filter({
        hasText: reason,
      });
      await radioLabel.click();
    } else {
      const firstRadio = this.page.locator(
        ".flag-modal input[type='radio'], .modal-body .flagging-topic input[type='radio']"
      ).first();
      await firstRadio.click();
    }

    const submitButton = this.page.locator(
      ".flag-modal .btn-primary, .modal-footer .btn-primary"
    ).filter({ hasText: /Flag Post|Flag/i });
    await submitButton.click();

    await this.page.waitForSelector(".flag-modal, .modal-body .flagging-topic", {
      state: "hidden",
      timeout: 10_000,
    });
  }

  async getFlagConfirmation(): Promise<boolean> {
    try {
      const confirmation = this.page.locator("text=/Thanks for flagging|successfully flagged/i");
      await confirmation.waitFor({ state: "visible", timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }
}
