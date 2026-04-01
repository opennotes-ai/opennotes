import { Page } from "playwright";

export class PostPage {
  constructor(private page: Page) {}

  async createTopic(title: string, body: string, category?: string): Promise<string> {
    await this.page.waitForTimeout(2000);
    const createBtn = this.page.locator("#create-topic, button:has-text('New Topic'), button.btn-default.no-text.btn-icon.ember-view");
    await createBtn.first().click({ timeout: 15000 });
    await this.page.waitForSelector(".d-editor-input, .d-editor textarea", { state: "visible", timeout: 15000 });

    const titleField = this.page.locator("#reply-title, .reply-area input.title-input");
    await titleField.first().fill(title);
    await this.page.locator(".d-editor-input, .d-editor textarea").first().fill(body);

    if (category) {
      await this.page.click(".category-chooser");
      await this.page.waitForSelector(".category-chooser .select-kit-body", { state: "visible" });
      const categoryOption = this.page
        .locator(".category-chooser .select-kit-row")
        .filter({ hasText: category });
      await categoryOption.click();
    }

    await this.page.locator(".save-or-cancel .create, button.btn-primary.create").first().click();
    await this.page.waitForTimeout(5000);

    return this.page.url();
  }

  async replyToTopic(body: string): Promise<void> {
    const replyButton = this.page.locator(".topic-footer-main-buttons button.create, button:has-text('Reply')");
    await replyButton.first().click();
    await this.page.waitForSelector(".d-editor-input, .d-editor textarea", { state: "visible" });
    await this.page.locator(".d-editor-input, .d-editor textarea").first().fill(body);
    await this.page.locator(".save-or-cancel .create, button.btn-primary.create").first().click();
    await this.page.waitForTimeout(3000);
  }

  async getPostContent(index: number): Promise<string> {
    await this.waitForTopicLoad();
    const posts = this.page.locator(".topic-post .cooked, article .cooked, .post-stream .cooked");
    const post = posts.nth(index);
    return (await post.textContent()) ?? "";
  }

  async getTopicTitle(): Promise<string> {
    await this.waitForTopicLoad();
    const title = this.page.locator(".fancy-title, .topic-title h1");
    return (await title.first().textContent()) ?? "";
  }

  async waitForTopicLoad(): Promise<void> {
    await this.page.waitForSelector(".topic-post, article[data-post-id], .post-stream .topic-body", {
      state: "visible",
      timeout: 15000,
    });
  }
}
