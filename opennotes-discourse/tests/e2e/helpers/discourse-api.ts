interface CreateUserResponse {
  success: boolean;
  active: boolean;
  user_id: number;
}

interface CategoryResponse {
  category: {
    id: number;
    name: string;
    slug: string;
  };
}

interface TopicResponse {
  topic_id: number;
  topic_slug: string;
  id: number;
}

interface UserListItem {
  id: number;
  username: string;
  email: string;
  trust_level: number;
}

export class DiscourseAPI {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(baseUrl: string, apiKey: string, apiUsername: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = {
      "Api-Key": apiKey,
      "Api-Username": apiUsername,
      "Content-Type": "application/json",
    };
  }

  private async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown>
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const options: RequestInit = {
      method,
      headers: this.headers,
    };
    if (body) {
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(
        `Discourse API ${method} ${path} failed (${response.status}): ${text}`
      );
    }
    if (response.status === 204) {
      return {} as T;
    }
    return response.json() as Promise<T>;
  }

  async getUserIdByUsername(username: string): Promise<number | undefined> {
    try {
      const resp = await this.request<{ user: { id: number } }>("GET", `/users/${username}.json`);
      return resp?.user?.id;
    } catch {
      return undefined;
    }
  }

  async createUser(
    username: string,
    email: string,
    password: string,
    trustLevel: number
  ): Promise<number> {
    const result = await this.request<CreateUserResponse>("POST", "/users.json", {
      name: username,
      username,
      email,
      password,
      active: true,
      approved: true,
    });

    let userId = result.user_id;

    if (!userId) {
      userId = await this.getUserIdByUsername(username) ?? 0;
    }

    if (userId && trustLevel > 0) {
      await this.request("PUT", `/admin/users/${userId}/trust_level.json`, {
        level: trustLevel,
      });
    }

    return userId;
  }

  async createCategory(
    name: string,
    slug: string,
    color?: string
  ): Promise<CategoryResponse["category"]> {
    try {
      const result = await this.request<CategoryResponse>("POST", "/categories.json", {
        name,
        slug,
        color: color ?? "0088CC",
        text_color: "FFFFFF",
      });
      return result.category;
    } catch (e: unknown) {
      if (e instanceof Error && (e.message.includes("422") || e.message.includes("429"))) {
        const resp = await this.request<Record<string, unknown>>("GET", "/categories.json");
        const catList = (resp as { category_list?: { categories?: CategoryResponse["category"][] } })
          .category_list?.categories ?? [];
        const found = catList.find(
          (c) => c.slug === slug || c.name === name
        );
        if (found) return found;
      }
      throw e;
    }
  }

  async createTopic(
    title: string,
    raw: string,
    categoryId: number
  ): Promise<TopicResponse> {
    return this.request<TopicResponse>("POST", "/posts.json", {
      title,
      raw,
      category: categoryId,
    });
  }

  async deleteTopic(topicId: number): Promise<void> {
    await this.request("DELETE", `/t/${topicId}.json`);
  }

  async getUsers(): Promise<UserListItem[]> {
    return this.request<UserListItem[]>(
      "GET",
      "/admin/users/list/active.json"
    );
  }

  async getSiteSettings(): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      "GET",
      "/admin/site_settings.json"
    );
  }

  async updateSiteSetting(name: string, value: string): Promise<void> {
    await this.request("PUT", `/admin/site_settings/${name}.json`, {
      [name]: value,
    });
  }
}
