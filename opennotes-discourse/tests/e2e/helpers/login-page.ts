import { Page } from "playwright";
import { ADMIN, REVIEWER1 } from "../fixtures/users";

export class LoginPage {
  constructor(private page: Page) {}

  async loginAs(username: string, password?: string): Promise<void> {
    const pwd = password ?? "password123";
    await this.page.goto("/login", { waitUntil: "domcontentloaded" });
    await this.page.waitForSelector("#login-account-name", { state: "visible", timeout: 30000 });
    await this.page.fill("#login-account-name", username);
    await this.page.fill("#login-account-password", pwd);
    await this.page.click("#login-button");
    await this.page.waitForSelector(".current-user", { state: "visible", timeout: 30000 });
  }

  async loginAsAdmin(): Promise<void> {
    await this.loginAs(ADMIN.email, ADMIN.password);
  }

  async loginAsReviewer(): Promise<void> {
    await this.loginAs(REVIEWER1.email, REVIEWER1.password);
  }

  async logout(): Promise<void> {
    await this.page.click(".current-user .icon");
    await this.page.waitForSelector(".user-menu-panel", { state: "visible" });
    const logoutButton = this.page.locator("button").filter({ hasText: "Log Out" });
    await logoutButton.click();
    const confirmButton = this.page.locator(".dialog-footer .btn-primary");
    if (await confirmButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await confirmButton.click();
    }
    await this.page.waitForSelector(".login-required, .login-button, .btn-primary:has-text('Log In')", { timeout: 15000 }).catch(() => {});
  }

  async isLoggedIn(): Promise<boolean> {
    try {
      await this.page.waitForSelector(".current-user", { state: "visible", timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }
}
