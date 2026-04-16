# frozen_string_literal: true

require "rails_helper"

RSpec.describe OpenNotes::PlatformRegistrar do
  let(:uuid) { "11111111-2222-3333-4444-555555555555" }
  let(:slug) { "forum.example.com-abcd1234" }
  let(:client) { instance_double(OpenNotes::Client) }

  before do
    SiteSetting.title = "My Forum"
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"
    SiteSetting.opennotes_platform_community_server_id = slug
    allow(Discourse).to receive(:current_hostname).and_return("forum.example.com")
    allow(OpenNotes::Client).to receive(:new).and_return(client)
    allow(OpenNotes::CommunityServerResolver).to receive(:community_server_id).and_return(uuid)
  end

  describe ".register" do
    it "PATCHes /name with SiteSetting.title and server_stats after resolving UUID" do
      expect(client).to receive(:patch).with(
        "/api/v1/community-servers/#{slug}/name",
        body: {
          name: "My Forum",
          server_stats: { platform: "discourse", hostname: "forum.example.com" },
        },
      ).and_return({})
      result = described_class.register
      expect(result[:ok]).to be true
      expect(result[:uuid]).to eq(uuid)
      expect(result[:name]).to eq("My Forum")
      expect(result[:slug]).to eq(slug)
    end

    it "returns missing_settings when server_url is blank" do
      SiteSetting.opennotes_server_url = ""
      expect(OpenNotes::Client).not_to receive(:new)
      result = described_class.register
      expect(result[:ok]).to be false
      expect(result[:reason]).to eq(:missing_settings)
    end

    it "returns missing_settings when api_key is blank" do
      SiteSetting.opennotes_api_key = ""
      expect(OpenNotes::Client).not_to receive(:new)
      result = described_class.register
      expect(result[:ok]).to be false
      expect(result[:reason]).to eq(:missing_settings)
    end

    it "returns missing_settings when platform_community_server_id is blank" do
      SiteSetting.opennotes_platform_community_server_id = ""
      expect(OpenNotes::Client).not_to receive(:new)
      result = described_class.register
      expect(result[:ok]).to be false
      expect(result[:reason]).to eq(:missing_settings)
    end

    it "returns lookup_failed when resolver returns nil" do
      allow(OpenNotes::CommunityServerResolver).to receive(:community_server_id).and_return(nil)
      expect(client).not_to receive(:patch)
      result = described_class.register
      expect(result[:ok]).to be false
      expect(result[:reason]).to eq(:lookup_failed)
    end

    it "returns api_error on OpenNotes::ApiError (does not raise)" do
      allow(client).to receive(:patch).and_raise(OpenNotes::ApiError.new(403, { "error" => "forbidden" }))
      expect(Rails.logger).to receive(:warn).with(/PATCH .*failed \(403\)/)
      result = described_class.register
      expect(result[:ok]).to be false
      expect(result[:reason]).to eq(:api_error)
      expect(result[:status]).to eq(403)
    end

    it "returns connection_error on Faraday::ConnectionFailed (does not raise)" do
      allow(client).to receive(:patch).and_raise(Faraday::ConnectionFailed.new("no route"))
      expect(Rails.logger).to receive(:warn).with(/connection failed/i)
      result = described_class.register
      expect(result[:ok]).to be false
      expect(result[:reason]).to eq(:connection_error)
    end
  end

  describe ".on_setting_saved" do
    it "is a no-op for unrelated settings" do
      expect(OpenNotes::CommunityServerResolver).not_to receive(:invalidate!)
      expect(described_class).not_to receive(:register)
      described_class.on_setting_saved(:title)
    end

    it "triggers registration when opennotes_server_url is saved" do
      allow(client).to receive(:patch).and_return({})
      expect(OpenNotes::CommunityServerResolver).not_to receive(:invalidate!)
      expect(described_class).to receive(:register).and_call_original
      described_class.on_setting_saved("opennotes_server_url")
    end

    it "triggers registration when opennotes_api_key is saved" do
      allow(client).to receive(:patch).and_return({})
      expect(described_class).to receive(:register).and_call_original
      described_class.on_setting_saved("opennotes_api_key")
    end

    it "invalidates resolver cache AND re-registers when slug changes" do
      allow(client).to receive(:patch).and_return({})
      expect(OpenNotes::CommunityServerResolver).to receive(:invalidate!).ordered
      expect(described_class).to receive(:register).ordered.and_call_original
      described_class.on_setting_saved("opennotes_platform_community_server_id")
    end

    it "logs info on success" do
      allow(client).to receive(:patch).and_return({})
      expect(Rails.logger).to receive(:info).with(/Registered community server/)
      described_class.on_setting_saved("opennotes_server_url")
    end

    it "logs warn on failure" do
      SiteSetting.opennotes_api_key = ""
      expect(Rails.logger).to receive(:warn).with(/Registration skipped or failed/)
      described_class.on_setting_saved("opennotes_server_url")
    end

    it "accepts symbol and string setting names interchangeably" do
      allow(client).to receive(:patch).and_return({})
      expect(described_class).to receive(:register).twice.and_call_original
      described_class.on_setting_saved(:opennotes_server_url)
      described_class.on_setting_saved("opennotes_api_key")
    end
  end
end
