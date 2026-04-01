import { Page } from "playwright";

export class AdminPage {
  constructor(private page: Page) {}

  async goToPlugins(): Promise<void> {
    await this.page.goto("/admin/plugins", { waitUntil: "domcontentloaded" });
    await this.page.waitForTimeout(3000);
  }

  async goToPluginSettings(pluginName: string): Promise<void> {
    await this.page.goto(`/admin/site_settings?filter=${pluginName}`, {
      waitUntil: "domcontentloaded",
    });
    await this.page.waitForTimeout(3000);
  }

  async getSettingValue(settingName: string): Promise<string> {
    const settingRow = this.page.locator(
      `[data-setting="${settingName}"], .admin-detail .setting-row, .admin-detail .row`
    ).filter({ hasText: settingName });

    const input = settingRow.locator(
      "input[type='text'], input[type='number'], input[type='password'], textarea, .setting-value .value"
    ).first();

    try {
      const tagName = await input.evaluate((el) => el.tagName.toLowerCase());
      if (tagName === "input" || tagName === "textarea") {
        return (await input.inputValue()) ?? "";
      }
      return (await input.textContent()) ?? "";
    } catch {
      return "";
    }
  }

  async setSettingValue(settingName: string, value: string): Promise<void> {
    const settingRow = this.page.locator(
      `[data-setting="${settingName}"], .admin-detail .setting-row, .admin-detail .row`
    ).filter({ hasText: settingName });

    const input = settingRow.locator(
      "input[type='text'], input[type='number'], textarea"
    ).first();
    await input.fill(value);

    const saveButton = settingRow.locator(
      ".setting-controls .ok, .setting-controls .btn-primary, button.ok"
    ).first();
    await saveButton.click();
    await this.page.waitForLoadState("domcontentloaded");
  }

  async goToDashboard(): Promise<void> {
    await this.page.goto("/admin", { waitUntil: "domcontentloaded" });
    await this.page.waitForTimeout(2000);
  }

  async isPluginInstalled(pluginName: string): Promise<boolean> {
    await this.page.waitForTimeout(3000);
    const text = await this.page.textContent("body");
    return text?.includes(pluginName) ?? false;
  }
}
