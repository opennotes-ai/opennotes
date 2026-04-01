export class OpenNotesAPI {
  private baseUrl: string;
  private apiKey: string;

  constructor(
    baseUrl: string = process.env.OPENNOTES_SERVER_URL ?? "http://127.0.0.1:8000",
    apiKey: string = process.env.OPENNOTES_API_KEY ?? "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c"
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  private get headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
      "X-Platform-Type": "discourse",
    };
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const options: RequestInit = {
      method,
      headers: this.headers,
    };
    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`OpenNotes API ${method} ${path} failed (${response.status}): ${text}`);
    }
    if (response.status === 204) {
      return {} as T;
    }
    return response.json() as Promise<T>;
  }

  async getRequests(filters?: Record<string, string>): Promise<any[]> {
    const params = filters ? "?" + new URLSearchParams(filters).toString() : "";
    const result = await this.request<{ data: any[] }>("GET", `/api/v2/requests${params}`);
    return result.data ?? [];
  }

  async getRequest(requestId: string): Promise<any> {
    const result = await this.request<{ data: any }>("GET", `/api/v2/requests/${requestId}`);
    return result.data;
  }

  async getNotes(requestId?: string): Promise<any[]> {
    const params = requestId ? `?filter[request_id]=${requestId}` : "";
    const result = await this.request<{ data: any[] }>("GET", `/api/v2/notes${params}`);
    return result.data ?? [];
  }

  async getNote(noteId: string): Promise<any> {
    const result = await this.request<{ data: any }>("GET", `/api/v2/notes/${noteId}`);
    return result.data;
  }

  async getRatings(noteId: string): Promise<any[]> {
    const result = await this.request<{ data: any[] }>("GET", `/api/v2/notes/${noteId}/ratings`);
    return result.data ?? [];
  }

  async getModerationAction(actionId: string): Promise<any> {
    const result = await this.request<{ data: any }>(
      "GET",
      `/api/v2/moderation-actions/${actionId}`
    );
    return result.data;
  }

  async getModerationActions(filters?: Record<string, string>): Promise<any[]> {
    const params = filters ? "?" + new URLSearchParams(filters).toString() : "";
    const result = await this.request<{ data: any[] }>(
      "GET",
      `/api/v2/moderation-actions${params}`
    );
    return result.data ?? [];
  }

  async getCommunityServer(communityServerId: string): Promise<any> {
    return this.request<any>(
      "GET",
      `/api/v1/community-servers/lookup?platform=discourse&platform_community_server_id=${encodeURIComponent(communityServerId)}`
    );
  }

  async getCommunityServers(): Promise<any[]> {
    const result = await this.request<any>("GET", `/api/v1/community-servers/lookup`);
    return Array.isArray(result) ? result : [result];
  }

  async getMonitoredChannels(communityServerId: string): Promise<any[]> {
    const result = await this.request<{ data: any[] }>(
      "GET",
      `/api/v2/monitored-channels?filter[community_server_id]=${encodeURIComponent(communityServerId)}`
    );
    return result.data ?? [];
  }

  async triggerScoring(communityServerId: string): Promise<void> {
    await this.request("POST", `/api/v2/community-servers/${communityServerId}/score`);
  }

  async getUserProfile(platform: string, userId: string, scope: string): Promise<any> {
    return this.request<any>(
      "GET",
      `/api/v2/profiles?filter[platform]=${encodeURIComponent(platform)}&filter[platform_user_id]=${encodeURIComponent(userId)}&scope=${encodeURIComponent(scope)}`
    );
  }

  async isHealthy(): Promise<boolean> {
    try {
      await fetch(`${this.baseUrl}/health`, { headers: this.headers });
      return true;
    } catch {
      return false;
    }
  }
}
