import { Page } from "@playwright/test";

export class DashboardPage {
  constructor(private page: Page) {}

  async goToDashboard(): Promise<void> {
    await this.page.goto("/admin/plugins/opennotes");
    await this.page.waitForLoadState("networkidle");
  }

  async waitForLoad(): Promise<void> {
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForSelector(".opennotes-admin-dashboard", { state: "visible" });
    await this.page.waitForSelector(".opennotes-admin-dashboard__loading", { state: "detached" });
  }

  async getActivityMetrics(): Promise<Record<string, unknown> | null> {
    const section = this.page.locator(".opennotes-admin-dashboard__section").first();
    const isVisible = await section.isVisible().catch(() => false);
    if (!isVisible) {
      return null;
    }

    const rows = await section.locator("tr").all();
    if (rows.length === 0) {
      return null;
    }

    const metrics: Record<string, unknown> = {};
    for (const row of rows) {
      const cells = await row.locator("td").all();
      if (cells.length >= 2) {
        const key = (await cells[0].textContent()) ?? "";
        const value = (await cells[1].textContent()) ?? "";
        metrics[key.trim()] = value.trim();
      }
    }
    return Object.keys(metrics).length > 0 ? metrics : null;
  }

  async getScoringHealth(): Promise<Record<string, unknown> | null> {
    const sections = await this.page.locator(".opennotes-admin-dashboard__section").all();
    if (sections.length < 3) {
      return null;
    }
    const consensusSection = sections[2];
    const rows = await consensusSection.locator("tr").all();
    if (rows.length === 0) {
      return null;
    }

    const metrics: Record<string, unknown> = {};
    for (const row of rows) {
      const cells = await row.locator("td").all();
      if (cells.length >= 2) {
        const key = (await cells[0].textContent()) ?? "";
        const value = (await cells[1].textContent()) ?? "";
        metrics[key.trim()] = value.trim();
      }
    }
    return Object.keys(metrics).length > 0 ? metrics : null;
  }

  async getTopReviewers(): Promise<Array<{ username: string; count: number }>> {
    const reviewerRows = await this.page
      .locator(".opennotes-admin-dashboard__section:last-child tbody tr")
      .all();
    const reviewers: Array<{ username: string; count: number }> = [];

    for (const row of reviewerRows) {
      const cells = await row.locator("td").all();
      if (cells.length >= 2) {
        const username = (await cells[0].textContent()) ?? "";
        const countText = (await cells[1].textContent()) ?? "0";
        reviewers.push({
          username: username.trim(),
          count: parseInt(countText.trim(), 10) || 0,
        });
      }
    }

    return reviewers;
  }

  async hasError(): Promise<boolean> {
    const errorEl = this.page.locator(".opennotes-admin-dashboard__error");
    return errorEl.isVisible().catch(() => false);
  }

  async isLoaded(): Promise<boolean> {
    const dashboard = this.page.locator(".opennotes-admin-dashboard");
    const isVisible = await dashboard.isVisible().catch(() => false);
    if (!isVisible) {
      return false;
    }
    const loading = this.page.locator(".opennotes-admin-dashboard__loading");
    const isLoading = await loading.isVisible().catch(() => false);
    return !isLoading;
  }
}
