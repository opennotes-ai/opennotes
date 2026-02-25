import { jest } from '@jest/globals';

type MockFetch = jest.Mock<typeof fetch>;

export function getFetchRequest(mockFetch: MockFetch, callIndex = 0): Request {
  return mockFetch.mock.calls[callIndex]![0] as Request;
}

export function getFetchRequestDetails(
  mockFetch: MockFetch,
  callIndex = 0
): { url: string; method: string; headers: Record<string, string> } {
  const request = getFetchRequest(mockFetch, callIndex);
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    headers[key] = value;
  });
  return { url: request.url, method: request.method, headers };
}

export async function getFetchRequestBody(
  mockFetch: MockFetch,
  callIndex = 0
): Promise<unknown> {
  const request = getFetchRequest(mockFetch, callIndex);
  return JSON.parse(await request.clone().text());
}
