# frozen_string_literal: true

RSpec.describe OpenNotes::UserMapper do
  let(:client) { instance_double(OpenNotes::Client) }
  let(:mapper) { described_class.new(client) }

  let(:discourse_user) do
    instance_double(
      "User",
      id: 42,
      username: "alice",
      trust_level: 2,
      admin?: false,
      moderator?: false,
    )
  end

  let(:profile_response) do
    {
      "data" => {
        "id" => "abc-123",
        "type" => "user-profiles",
        "attributes" => {
          "display_name" => "alice",
          "reputation" => 0,
        },
      },
    }
  end

  before do
    SiteSetting.opennotes_platform_community_server_id = "community.example.com-abcd1234"
    allow(Discourse).to receive(:current_hostname).and_return("community.example.com")
  end

  describe "#lookup_or_create" do
    it "calls the server lookup endpoint with slug as provider_scope" do
      expect(client).to receive(:get).with(
        "#{OpenNotes::PUBLIC_API_PREFIX}/user-profiles/lookup",
        params: {
          platform: "discourse",
          platform_user_id: "42",
          provider_scope: "community.example.com-abcd1234",
        },
        user: discourse_user,
      ).and_return(profile_response)

      result = mapper.lookup_or_create(discourse_user)
      expect(result).to eq(profile_response)
    end

    it "returns nil when the server returns 404" do
      allow(client).to receive(:get).and_raise(
        OpenNotes::ApiError.new(404, { "error" => "not found" })
      )

      result = mapper.lookup_or_create(discourse_user)
      expect(result).to be_nil
    end

    it "re-raises non-404 API errors" do
      allow(client).to receive(:get).and_raise(
        OpenNotes::ApiError.new(500, { "error" => "server error" })
      )

      expect { mapper.lookup_or_create(discourse_user) }.to raise_error(OpenNotes::ApiError)
    end

    it "caches the result for 15 minutes" do
      expect(client).to receive(:get).once.and_return(profile_response)

      mapper.lookup_or_create(discourse_user)
      result = mapper.lookup_or_create(discourse_user)
      expect(result).to eq(profile_response)
    end

    it "refreshes the cache after expiry" do
      expect(client).to receive(:get).twice.and_return(profile_response)

      mapper.lookup_or_create(discourse_user)

      allow(Time).to receive(:now).and_return(Time.now + (16 * 60))
      mapper.lookup_or_create(discourse_user)
    end

    it "does not cache nil results" do
      allow(client).to receive(:get).and_raise(
        OpenNotes::ApiError.new(404, { "error" => "not found" })
      )

      mapper.lookup_or_create(discourse_user)

      allow(client).to receive(:get).and_return(profile_response)
      result = mapper.lookup_or_create(discourse_user)
      expect(result).to eq(profile_response)
    end
  end
end
