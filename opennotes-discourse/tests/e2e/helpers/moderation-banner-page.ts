import { Page } from "@playwright/test";

export class ModerationBannerPage {
  constructor(private page: Page) {}

  async getReviewBanner(postSelector?: string): Promise<string | null> {
    const container = postSelector ? this.page.locator(postSelector) : this.page;
    const banner = container.locator(".opennotes-review-banner--warning").first();
    const isVisible = await banner.isVisible().catch(() => false);
    if (!isVisible) {
      return null;
    }
    return banner.textContent();
  }

  async getConsensusBadge(postSelector?: string): Promise<string | null> {
    const container = postSelector ? this.page.locator(postSelector) : this.page;
    const badge = container.locator(".opennotes-badge").first();
    const isVisible = await badge.isVisible().catch(() => false);
    if (!isVisible) {
      return null;
    }
    return badge.textContent();
  }

  async getStaffAnnotation(postSelector?: string): Promise<string | null> {
    const container = postSelector ? this.page.locator(postSelector) : this.page;
    const annotation = container.locator(".opennotes-staff-annotation").first();
    const isVisible = await annotation.isVisible().catch(() => false);
    if (!isVisible) {
      return null;
    }
    return annotation.textContent();
  }

  async isPostHidden(): Promise<boolean> {
    const hiddenEl = this.page.locator(".cooked.hidden, .post-hidden, .topic-status-hidden");
    return hiddenEl.isVisible().catch(() => false);
  }

  async isUnderReview(): Promise<boolean> {
    const warningBanner = this.page.locator(".opennotes-review-banner--warning");
    const dangerBanner = this.page.locator(".opennotes-review-banner--danger");
    const warningVisible = await warningBanner.isVisible().catch(() => false);
    const dangerVisible = await dangerBanner.isVisible().catch(() => false);
    return warningVisible || dangerVisible;
  }
}
