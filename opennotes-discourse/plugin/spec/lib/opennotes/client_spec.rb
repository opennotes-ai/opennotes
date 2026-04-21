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
    SiteSetting.opennotes_platform_community_server_id = "community.example.com-abcd1234"
    allow(Discourse).to receive(:current_hostname).and_return("community.example.com")
    OpenNotes::GcpAuth.reset_cache!
    client.instance_variable_set(:@connection, test_connection)
    allow(OpenNotes::GcpAuth).to receive(:on_gcp?).and_return(false)
  end

  describe "server_url normalization" do
    it "strips a trailing slash so Cloud Run ID token audience matches exactly" do
      trailing = described_class.new(server_url: "https://opennotes.example.com/", api_key: api_key)
      expect(trailing.server_url).to eq("https://opennotes.example.com")

      plain = described_class.new(server_url: "https://opennotes.example.com", api_key: api_key)
      expect(plain.server_url).to eq("https://opennotes.example.com")
    end

    it "passes the normalized audience to identity_token on GCP" do
      trailing = described_class.new(server_url: "https://opennotes.example.com/", api_key: api_key)
      trailing.instance_variable_set(:@connection, test_connection)

      allow(OpenNotes::GcpAuth).to receive(:on_gcp?).and_return(true)
      expect(OpenNotes::GcpAuth).to receive(:identity_token)
        .with("https://opennotes.example.com")
        .and_return("fake-id-token")

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      trailing.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
    end
  end

  shared_examples "sets auth headers from GCP state" do |verb:, path:, faraday_verb: verb|
    it "sets X-API-Key and no Authorization when off GCP (#{verb.upcase})" do
      stubs.public_send(faraday_verb, path) do |env|
        expect(env.request_headers["X-API-Key"]).to eq("test-api-key")
        expect(env.request_headers).not_to have_key("Authorization")
        [200, { "Content-Type" => "application/json" }, "{}"]
      end

      client.public_send(verb, path)
    end

    it "sets both X-API-Key and Authorization: Bearer <id_token> when on GCP (#{verb.upcase})" do
      allow(OpenNotes::GcpAuth).to receive(:on_gcp?).and_return(true)
      allow(OpenNotes::GcpAuth).to receive(:identity_token).with(server_url).and_return("fake-id-token")

      stubs.public_send(faraday_verb, path) do |env|
        expect(env.request_headers["X-API-Key"]).to eq("test-api-key")
        expect(env.request_headers["Authorization"]).to eq("Bearer fake-id-token")
        [200, { "Content-Type" => "application/json" }, "{}"]
      end

      client.public_send(verb, path)
    end
  end

  describe "auth headers across verbs" do
    include_examples "sets auth headers from GCP state",
                     verb: :get, path: "/cross-verb-get"
    include_examples "sets auth headers from GCP state",
                     verb: :post, path: "/cross-verb-post"
    include_examples "sets auth headers from GCP state",
                     verb: :patch, path: "/cross-verb-patch"
    include_examples "sets auth headers from GCP state",
                     verb: :delete, path: "/cross-verb-delete"
  end

  after do
    stubs.verify_stubbed_calls
  end

  describe "#get" do
    it "sends a GET request with the API key in X-API-Key and no Authorization header when off GCP" do
      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        expect(env.request_headers["X-API-Key"]).to eq("test-api-key")
        expect(env.request_headers).not_to have_key("Authorization")
        expect(env.request_headers).not_to have_key("X-Platform-Type")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      result = client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
      expect(result).to eq("data" => [])
    end

    it "sends both X-API-Key and Authorization: Bearer <id_token> when on GCP" do
      allow(OpenNotes::GcpAuth).to receive(:on_gcp?).and_return(true)
      allow(OpenNotes::GcpAuth).to receive(:identity_token).with(server_url).and_return("fake-id-token")

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        expect(env.request_headers["X-API-Key"]).to eq("test-api-key")
        expect(env.request_headers["Authorization"]).to eq("Bearer fake-id-token")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
    end

    it "still sends X-API-Key when on GCP but identity token fetch returns nil" do
      allow(OpenNotes::GcpAuth).to receive(:on_gcp?).and_return(true)
      allow(OpenNotes::GcpAuth).to receive(:identity_token).with(server_url).and_return(nil)

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        expect(env.request_headers["X-API-Key"]).to eq("test-api-key")
        expect(env.request_headers).not_to have_key("Authorization")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
    end

    it "includes adapter headers when user is provided" do
      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        expect(env.request_headers["X-Adapter-Platform"]).to eq("discourse")
        expect(env.request_headers["X-Adapter-User-Id"]).to eq("42")
        expect(env.request_headers["X-Adapter-Username"]).to eq("alice")
        expect(env.request_headers["X-Adapter-Trust-Level"]).to eq("2")
        expect(env.request_headers["X-Adapter-Admin"]).to eq("false")
        expect(env.request_headers["X-Adapter-Moderator"]).to eq("false")
        expect(env.request_headers["X-Adapter-Scope"]).to eq("community.example.com-abcd1234")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests", user: user)
    end

    it "does not include adapter headers when no user is provided" do
      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        expect(env.request_headers).not_to have_key("X-Adapter-Platform")
        expect(env.request_headers).not_to have_key("X-Adapter-User-Id")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
    end

    it "passes query parameters" do
      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        expect(env.url.query).to include("filter")
        expect(env.url.query).to include("pending")
        [200, { "Content-Type" => "application/json" }, '{"data": []}']
      end

      client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests", params: { "filter[status]" => "pending" })
    end
  end

  describe "#post" do
    it "sends a POST request with JSON body" do
      body = { data: { type: "requests", attributes: { content: "test" } } }

      stubs.post("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |env|
        parsed = JSON.parse(env.body)
        expect(parsed["data"]["type"]).to eq("requests")
        [201, { "Content-Type" => "application/json" }, '{"data": {"id": "123"}}']
      end

      result = client.post("#{OpenNotes::PUBLIC_API_PREFIX}/requests", body: body)
      expect(result).to eq("data" => { "id" => "123" })
    end
  end

  describe "#patch" do
    it "sends a PATCH request with JSON body" do
      body = { data: { type: "requests", attributes: { status: "completed" } } }

      stubs.patch("#{OpenNotes::PUBLIC_API_PREFIX}/requests/123") do |env|
        parsed = JSON.parse(env.body)
        expect(parsed["data"]["attributes"]["status"]).to eq("completed")
        [200, { "Content-Type" => "application/json" }, '{"data": {"id": "123"}}']
      end

      result = client.patch("#{OpenNotes::PUBLIC_API_PREFIX}/requests/123", body: body)
      expect(result).to eq("data" => { "id" => "123" })
    end

    it "passes query parameters on PATCH requests" do
      stubs.patch("#{OpenNotes::PUBLIC_API_PREFIX}/requests/123") do |env|
        expect(env.url.query).to include("platform")
        expect(env.url.query).to include("discourse")
        [200, { "Content-Type" => "application/json" }, '{"data": {"id": "123"}}']
      end

      client.patch("#{OpenNotes::PUBLIC_API_PREFIX}/requests/123", params: { platform: "discourse" }, body: {})
    end
  end

  describe "#delete" do
    it "sends a DELETE request" do
      stubs.delete("#{OpenNotes::PUBLIC_API_PREFIX}/requests/123") do |_env|
        [204, { "Content-Type" => "application/json" }, ""]
      end

      result = client.delete("#{OpenNotes::PUBLIC_API_PREFIX}/requests/123")
      expect(result).to be_nil
    end
  end

  describe "retry behavior" do
    it "retries on 429 status with exponential backoff" do
      attempt = 0

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        attempt += 1
        if attempt < 3
          [429, { "Content-Type" => "application/json" }, '{"error": "rate limited"}']
        else
          [200, { "Content-Type" => "application/json" }, '{"data": []}']
        end
      end

      allow(client).to receive(:sleep)
      result = client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
      expect(result).to eq("data" => [])
      expect(attempt).to eq(3)
    end

    it "retries on 500 status" do
      attempt = 0

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        attempt += 1
        if attempt == 1
          [500, { "Content-Type" => "application/json" }, '{"error": "server error"}']
        else
          [200, { "Content-Type" => "application/json" }, '{"data": []}']
        end
      end

      allow(client).to receive(:sleep)
      result = client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests")
      expect(result).to eq("data" => [])
    end

    it "raises ApiError after max retries exhausted" do
      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        [503, { "Content-Type" => "application/json" }, '{"error": "unavailable"}']
      end

      allow(client).to receive(:sleep)
      expect { client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") }.to raise_error(OpenNotes::ApiError) do |error|
        expect(error.status).to eq(503)
      end
    end

    it "does not retry on 400 client errors" do
      attempt = 0

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        attempt += 1
        [400, { "Content-Type" => "application/json" }, '{"error": "bad request"}']
      end

      expect { client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") }.to raise_error(OpenNotes::ApiError)
      expect(attempt).to eq(1)
    end

    it "does not retry on 404" do
      attempt = 0

      stubs.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        attempt += 1
        [404, { "Content-Type" => "application/json" }, '{"error": "not found"}']
      end

      expect { client.get("#{OpenNotes::PUBLIC_API_PREFIX}/requests") }.to raise_error(OpenNotes::ApiError)
      expect(attempt).to eq(1)
    end
  end

  describe "error handling" do
    it "raises ApiError with status and body on non-retryable errors" do
      stubs.post("#{OpenNotes::PUBLIC_API_PREFIX}/requests") do |_env|
        [422, { "Content-Type" => "application/json" }, '{"errors": [{"detail": "invalid"}]}']
      end

      expect { client.post("#{OpenNotes::PUBLIC_API_PREFIX}/requests", body: {}) }.to raise_error(OpenNotes::ApiError) do |error|
        expect(error.status).to eq(422)
        expect(error.body).to eq("errors" => [{ "detail" => "invalid" }])
        expect(error.message).to include("422")
      end
    end
  end
end
