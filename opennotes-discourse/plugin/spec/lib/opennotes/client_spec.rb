# frozen_string_literal: true

RSpec.describe OpenNotes::Client do
  let(:server_url) { "https://opennotes.example.com" }
  let(:api_key) { "test-api-key" }
  let(:client) { described_class.new(server_url: server_url, api_key: api_key) }

  let(:user) do
    instance_double(
      "User",
      id: 42,
      username: "alice",
      trust_level: 2,
      admin?: false,
      moderator?: false,
    )
  end

  let(:stubs) { Faraday::Adapter::Test::Stubs.new }
  let(:test_connection) do
    Faraday.new(url: server_url) do |f|
      f.request :json
      f.response :json
      f.adapter :test, stubs
    end
  end

  before do
    allow(Discourse).to receive(:current_hostname).and_return("community.example.com")
    client.instance_variable_set(:@connection, test_connection)
  end

  after do
    stubs.verify_stubbed_calls
  end

  describe "#get" do
    it "sends a GET request with authorization headers" do
      stubs.get("/api/v2/requests") do |env|
        expect(env.request_headers["Authorization"]).to eq("Bearer test-api-key")
        expect(env.request_headers["X-Platform-Type"]).to eq("discourse")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      result = client.get("/api/v2/requests")
      expect(result).to eq("data" => [])
    end

    it "includes adapter headers when user is provided" do
      stubs.get("/api/v2/requests") do |env|
        expect(env.request_headers["X-Adapter-Platform"]).to eq("discourse")
        expect(env.request_headers["X-Adapter-User-Id"]).to eq("42")
        expect(env.request_headers["X-Adapter-Username"]).to eq("alice")
        expect(env.request_headers["X-Adapter-Trust-Level"]).to eq("2")
        expect(env.request_headers["X-Adapter-Admin"]).to eq("false")
        expect(env.request_headers["X-Adapter-Moderator"]).to eq("false")
        expect(env.request_headers["X-Adapter-Scope"]).to eq("community.example.com")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("/api/v2/requests", user: user)
    end

    it "does not include adapter headers when no user is provided" do
      stubs.get("/api/v2/requests") do |env|
        expect(env.request_headers).not_to have_key("X-Adapter-Platform")
        expect(env.request_headers).not_to have_key("X-Adapter-User-Id")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("/api/v2/requests")
    end

    it "passes query parameters" do
      stubs.get("/api/v2/requests") do |env|
        expect(env.url.query).to include("filter")
        expect(env.url.query).to include("pending")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("/api/v2/requests", params: { "filter[status]" => "pending" })
    end
  end

  describe "#post" do
    it "sends a POST request with JSON body" do
      body = { data: { type: "requests", attributes: { content: "test" } } }

      stubs.post("/api/v2/requests") do |env|
        parsed = JSON.parse(env.body)
        expect(parsed["data"]["type"]).to eq("requests")
        [201, { "Content-Type" => "application/json" }, '{"data": {"id": "123"}}']
      end

      result = client.post("/api/v2/requests", body: body)
      expect(result).to eq("data" => { "id" => "123" })
    end
  end

  describe "#patch" do
    it "sends a PATCH request with JSON body" do
      body = { data: { type: "requests", attributes: { status: "completed" } } }

      stubs.patch("/api/v2/requests/123") do |env|
        parsed = JSON.parse(env.body)
        expect(parsed["data"]["attributes"]["status"]).to eq("completed")
        [200, { "Content-Type" => "application/json" }, '{"data": {"id": "123"}}']
      end

      result = client.patch("/api/v2/requests/123", body: body)
      expect(result).to eq("data" => { "id" => "123" })
    end
  end

  describe "#delete" do
    it "sends a DELETE request" do
      stubs.delete("/api/v2/requests/123") do |_env|
        [204, { "Content-Type" => "application/json" }, ""]
      end

      result = client.delete("/api/v2/requests/123")
      expect(result).to be_nil
    end
  end

  describe "retry behavior" do
    it "retries on 429 status with exponential backoff" do
      attempt = 0

      stubs.get("/api/v2/requests") do |_env|
        attempt += 1
        if attempt < 3
          [429, { "Content-Type" => "application/json" }, '{"error": "rate limited"}']
        else
          [200, { "Content-Type" => "application/json" }, '{"data": []}']
        end
      end

      allow(client).to receive(:sleep)
      result = client.get("/api/v2/requests")
      expect(result).to eq("data" => [])
      expect(attempt).to eq(3)
    end

    it "retries on 500 status" do
      attempt = 0

      stubs.get("/api/v2/requests") do |_env|
        attempt += 1
        if attempt == 1
          [500, { "Content-Type" => "application/json" }, '{"error": "server error"}']
        else
          [200, { "Content-Type" => "application/json" }, '{"data": []}']
        end
      end

      allow(client).to receive(:sleep)
      result = client.get("/api/v2/requests")
      expect(result).to eq("data" => [])
    end

    it "raises ApiError after max retries exhausted" do
      stubs.get("/api/v2/requests") do |_env|
        [503, { "Content-Type" => "application/json" }, '{"error": "unavailable"}']
      end

      allow(client).to receive(:sleep)
      expect { client.get("/api/v2/requests") }.to raise_error(OpenNotes::ApiError) do |error|
        expect(error.status).to eq(503)
      end
    end

    it "does not retry on 400 client errors" do
      attempt = 0

      stubs.get("/api/v2/requests") do |_env|
        attempt += 1
        [400, { "Content-Type" => "application/json" }, '{"error": "bad request"}']
      end

      expect { client.get("/api/v2/requests") }.to raise_error(OpenNotes::ApiError)
      expect(attempt).to eq(1)
    end

    it "does not retry on 404" do
      attempt = 0

      stubs.get("/api/v2/requests") do |_env|
        attempt += 1
        [404, { "Content-Type" => "application/json" }, '{"error": "not found"}']
      end

      expect { client.get("/api/v2/requests") }.to raise_error(OpenNotes::ApiError)
      expect(attempt).to eq(1)
    end
  end

  describe "error handling" do
    it "raises ApiError with status and body on non-retryable errors" do
      stubs.post("/api/v2/requests") do |_env|
        [422, { "Content-Type" => "application/json" }, '{"errors": [{"detail": "invalid"}]}']
      end

      expect { client.post("/api/v2/requests", body: {}) }.to raise_error(OpenNotes::ApiError) do |error|
        expect(error.status).to eq(422)
        expect(error.body).to eq("errors" => [{ "detail" => "invalid" }])
        expect(error.message).to include("422")
      end
    end
  end
end
