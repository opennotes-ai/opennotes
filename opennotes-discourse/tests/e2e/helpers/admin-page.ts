import { Page } from "playwright";

export class AdminPage {
  constructor(private page: Page) {}

  async goToPlugins(): Promise<void> {
    await this.page.goto("/admin/plugins");
    await this.page.waitForLoadState("networkidle");
  }

  async goToPluginSettings(pluginName: string): Promise<void> {
    await this.page.goto(`/admin/site_settings?filter=plugin%3A${pluginName}`);
    await this.page.waitForLoadState("networkidle");
  }

  async getSettingValue(settingName: string): Promise<string> {
    const settingRow = this.page.locator(
      `.admin-detail .setting-row, .admin-detail .row`
    ).filter({ hasText: settingName });

    const input = settingRow.locator(
      "input[type='text'], input[type='number'], textarea, .setting-value .value"
    ).first();

    const tagName = await input.evaluate((el) => el.tagName.toLowerCase());
    if (tagName === "input" || tagName === "textarea") {
      return (await input.inputValue()) ?? "";
    }
    return (await input.textContent()) ?? "";
  }

  async setSettingValue(settingName: string, value: string): Promise<void> {
    const settingRow = this.page.locator(
      `.admin-detail .setting-row, .admin-detail .row`
    ).filter({ hasText: settingName });

    const input = settingRow.locator(
      "input[type='text'], input[type='number'], textarea"
    ).first();
    await input.fill(value);

    const saveButton = settingRow.locator(
      ".setting-controls .ok, .setting-controls .btn-primary, button.ok"
    ).first();
    await saveButton.click();
    await this.page.waitForLoadState("networkidle");
  }

  async goToDashboard(): Promise<void> {
    await this.page.goto("/admin");
    await this.page.waitForLoadState("networkidle");
  }

  async isPluginInstalled(pluginName: string): Promise<boolean> {
    await this.page.waitForLoadState("networkidle");
    const pluginRow = this.page.locator(
      ".admin-plugins .admin-plugin, tr, .plugin-list-item"
    ).filter({ hasText: pluginName });
    return (await pluginRow.count()) > 0;
  }
}
