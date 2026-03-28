import { Page } from "playwright";

export class NavigationPage {
  constructor(private page: Page) {}

  async goToCategory(name: string): Promise<void> {
    const slug = name.toLowerCase().replace(/\s+/g, "-");
    await this.page.goto(`/c/${slug}`);
    await this.page.waitForLoadState("networkidle");
  }

  async goToAdminPlugins(): Promise<void> {
    await this.page.goto("/admin/plugins");
    await this.page.waitForLoadState("networkidle");
  }

  async goToAdminSettings(filter?: string): Promise<void> {
    const url = filter
      ? `/admin/site_settings?filter=${encodeURIComponent(filter)}`
      : "/admin/site_settings";
    await this.page.goto(url);
    await this.page.waitForLoadState("networkidle");
  }

  async goToReviewQueue(): Promise<void> {
    await this.page.goto("/review");
    await this.page.waitForLoadState("networkidle");
  }

  async goToLatest(): Promise<void> {
    await this.page.goto("/latest");
    await this.page.waitForLoadState("networkidle");
  }

  getCurrentPath(): string {
    return new URL(this.page.url()).pathname;
  }
}
