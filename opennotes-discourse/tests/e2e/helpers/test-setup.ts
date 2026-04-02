import { execSync } from "child_process";
import * as path from "path";
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

  async seedServerData(sqlFile?: string): Promise<void> {
    const seedFile =
      sqlFile ?? path.resolve(__dirname, "../fixtures/server-seed.sql");
    const pgUser = process.env.POSTGRES_USER ?? "opennotes";
    const pgDb = process.env.POSTGRES_DB ?? "opennotes";
    const pgHost = process.env.POSTGRES_HOST ?? "127.0.0.1";
    const pgPort = process.env.POSTGRES_PORT ?? "5432";

    execSync(
      `psql -h ${pgHost} -p ${pgPort} -U ${pgUser} -d ${pgDb} -f "${seedFile}"`,
      {
        env: {
          ...process.env,
          PGPASSWORD: process.env.POSTGRES_PASSWORD ?? "testpass",
        },
        stdio: "pipe",
      }
    );
  }

  async resetServerData(): Promise<void> {
    const pgUser = process.env.POSTGRES_USER ?? "opennotes";
    const pgDb = process.env.POSTGRES_DB ?? "opennotes";
    const pgHost = process.env.POSTGRES_HOST ?? "127.0.0.1";
    const pgPort = process.env.POSTGRES_PORT ?? "5432";

    const sql = `
      DELETE FROM moderation_actions
        WHERE community_server_id IN (
          SELECT id FROM community_servers
          WHERE platform = 'discourse' AND platform_community_server_id = 'discourse-dev-1'
        );
      DELETE FROM ratings
        WHERE note_id IN (
          SELECT id FROM notes
            WHERE community_server_id IN (
              SELECT id FROM community_servers
              WHERE platform = 'discourse' AND platform_community_server_id = 'discourse-dev-1'
            )
        );
      DELETE FROM notes
        WHERE community_server_id IN (
          SELECT id FROM community_servers
          WHERE platform = 'discourse' AND platform_community_server_id = 'discourse-dev-1'
        );
      DELETE FROM requests
        WHERE community_server_id IN (
          SELECT id FROM community_servers
          WHERE platform = 'discourse' AND platform_community_server_id = 'discourse-dev-1'
        );
    `;

    execSync(
      `psql -h ${pgHost} -p ${pgPort} -U ${pgUser} -d ${pgDb} -c "${sql.replace(/"/g, '\\"')}"`,
      {
        env: {
          ...process.env,
          PGPASSWORD: process.env.POSTGRES_PASSWORD ?? "testpass",
        },
        stdio: "pipe",
      }
    );
  }
}
