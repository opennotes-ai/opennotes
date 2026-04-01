import { Page } from "playwright";

export class NavigationPage {
  constructor(private page: Page) {}

  async goToCategory(name: string): Promise<void> {
    const slug = name.toLowerCase().replace(/\s+/g, "-");
    await this.page.goto(`/c/${slug}`);
    await this.page.waitForLoadState("domcontentloaded");
  }

  async goToAdminPlugins(): Promise<void> {
    await this.page.goto("/admin/plugins");
    await this.page.waitForLoadState("domcontentloaded");
  }

  async goToAdminSettings(filter?: string): Promise<void> {
    const url = filter
      ? `/admin/site_settings?filter=${encodeURIComponent(filter)}`
      : "/admin/site_settings";
    await this.page.goto(url);
    await this.page.waitForLoadState("domcontentloaded");
  }

  async goToReviewQueue(): Promise<void> {
    await this.page.goto("/review");
    await this.page.waitForLoadState("domcontentloaded");
  }

  async goToLatest(): Promise<void> {
    await this.page.goto("/latest");
    await this.page.waitForLoadState("domcontentloaded");
  }

  getCurrentPath(): string {
    return new URL(this.page.url()).pathname;
  }
}
