import { DiscourseAPI } from "./discourse-api";
import { ALL_USERS, ADMIN, TestUser } from "../fixtures/users";

export class TestSetup {
  private api: DiscourseAPI;

  constructor(api: DiscourseAPI) {
    this.api = api;
  }

  async ensureUsersExist(users?: TestUser[]): Promise<void> {
    const targetUsers = users ?? ALL_USERS;
    const existingUsers = await this.api.getUsers();
    const existingUsernames = new Set(existingUsers.map((u) => u.username));

    for (const user of targetUsers) {
      if (!existingUsernames.has(user.username)) {
        await this.api.createUser(
          user.username,
          user.email,
          user.password,
          user.trustLevel
        );
      }
    }
  }

  async createTestCategory(
    name: string,
    slug: string
  ): Promise<{ id: number; name: string; slug: string }> {
    return this.api.createCategory(name, slug);
  }

  async createTestTopic(
    title: string,
    body: string,
    categoryId: number
  ): Promise<{ topicId: number; topicSlug: string }> {
    const result = await this.api.createTopic(title, body, categoryId);
    return { topicId: result.topic_id, topicSlug: result.topic_slug };
  }

  async cleanupTopic(topicId: number): Promise<void> {
    await this.api.deleteTopic(topicId);
  }

  async updateSetting(name: string, value: string): Promise<void> {
    await this.api.updateSiteSetting(name, value);
  }

  getAPI(): DiscourseAPI {
    return this.api;
  }
}
