import { Page } from "playwright";

interface ReviewableItem {
  title: string;
  type: string;
  createdBy: string;
}

export class ReviewPage {
  constructor(private page: Page) {}

  async goToReviewQueue(): Promise<void> {
    await this.page.goto("/review");
    await this.page.waitForLoadState("networkidle");
  }

  async getReviewableCount(): Promise<number> {
    await this.page.waitForLoadState("networkidle");
    const items = this.page.locator(".reviewable-item");
    return items.count();
  }

  async getReviewableItems(): Promise<ReviewableItem[]> {
    await this.page.waitForLoadState("networkidle");
    const items = this.page.locator(".reviewable-item");
    const count = await items.count();
    const results: ReviewableItem[] = [];

    for (let i = 0; i < count; i++) {
      const item = items.nth(i);
      const title =
        (await item.locator(".reviewable-item-title, .topic-title, .title").first().textContent()) ?? "";
      const type =
        (await item
          .locator(".reviewable-type, .reviewable-item-type, .badge-type")
          .first()
          .textContent()
          .catch(() => "")) ?? "";
      const createdBy =
        (await item
          .locator(".created-by .username, .reviewable-item-created-by, a[data-user-card]")
          .first()
          .textContent()
          .catch(() => "")) ?? "";

      results.push({
        title: title.trim(),
        type: type.trim(),
        createdBy: createdBy.trim(),
      });
    }

    return results;
  }

  async approveItem(index: number): Promise<void> {
    const items = this.page.locator(".reviewable-item");
    const item = items.nth(index);
    const approveButton = item.locator(
      ".reviewable-actions .btn.approve, .reviewable-actions button"
    ).filter({ hasText: /Approve/i });
    await approveButton.click();
    await this.page.waitForLoadState("networkidle");
  }

  async rejectItem(index: number): Promise<void> {
    const items = this.page.locator(".reviewable-item");
    const item = items.nth(index);
    const rejectButton = item.locator(
      ".reviewable-actions .btn.reject, .reviewable-actions button"
    ).filter({ hasText: /Reject|Delete/i });
    await rejectButton.click();
    await this.page.waitForLoadState("networkidle");
  }
}
