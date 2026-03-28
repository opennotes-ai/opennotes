import { Page } from "playwright";

export class PostPage {
  constructor(private page: Page) {}

  async createTopic(title: string, body: string, category?: string): Promise<string> {
    await this.page.click("#create-topic");
    await this.page.waitForSelector(".d-editor-input", { state: "visible" });

    await this.page.fill("#reply-title", title);
    await this.page.fill(".d-editor-input", body);

    if (category) {
      await this.page.click(".category-chooser");
      await this.page.waitForSelector(".category-chooser .select-kit-body", { state: "visible" });
      const categoryOption = this.page
        .locator(".category-chooser .select-kit-row")
        .filter({ hasText: category });
      await categoryOption.click();
    }

    await this.page.click(".create");
    await this.page.waitForSelector(".d-editor-input", { state: "hidden", timeout: 15_000 });
    await this.page.waitForLoadState("networkidle");

    return this.page.url();
  }

  async replyToTopic(body: string): Promise<void> {
    const replyButton = this.page.locator(".topic-footer-main-buttons .create");
    await replyButton.click();
    await this.page.waitForSelector(".d-editor-input", { state: "visible" });
    await this.page.fill(".d-editor-input", body);
    await this.page.click(".save-or-cancel .create");
    await this.page.waitForSelector(".d-editor-input", { state: "hidden", timeout: 15_000 });
    await this.page.waitForLoadState("networkidle");
  }

  async getPostContent(index: number): Promise<string> {
    await this.waitForTopicLoad();
    const posts = this.page.locator(".topic-post .cooked");
    const post = posts.nth(index);
    return (await post.textContent()) ?? "";
  }

  async getTopicTitle(): Promise<string> {
    await this.waitForTopicLoad();
    const title = this.page.locator(".fancy-title");
    return (await title.textContent()) ?? "";
  }

  async waitForTopicLoad(): Promise<void> {
    await this.page.waitForSelector(".topic-post", { state: "visible", timeout: 10_000 });
  }
}
