# frozen_string_literal: true

require "rails_helper"

RSpec.describe OpenNotes::CommunityServerResolver do
  let(:uuid) { "11111111-2222-3333-4444-555555555555" }
  let(:slug) { "forum.example.com-abcd1234" }

  before do
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"
    SiteSetting.opennotes_platform_community_server_id = slug
    Discourse.cache.delete(described_class::CACHE_KEY)
    ::PluginStore.remove(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY)
  end

  describe ".community_server_uuid" do
    context "when Discourse.cache is warm" do
      it "returns the cached UUID without hitting PluginStore or API" do
        Discourse.cache.write(described_class::CACHE_KEY, uuid, expires_in: 5.minutes)
        expect(::PluginStore).not_to receive(:get)
        expect(OpenNotes::Client).not_to receive(:new)
        expect(described_class.community_server_uuid).to eq(uuid)
      end
    end

    context "when Discourse.cache is cold but PluginStore has the UUID" do
      it "returns the stored UUID and warms the cache" do
        ::PluginStore.set(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY, uuid)
        expect(OpenNotes::Client).not_to receive(:new)
        expect(described_class.community_server_uuid).to eq(uuid)
        expect(Discourse.cache.read(described_class::CACHE_KEY)).to eq(uuid)
      end
    end

    context "when both layers are cold" do
      let(:client) { instance_double(OpenNotes::Client) }

      before do
        allow(OpenNotes::Client).to receive(:new).and_return(client)
      end

      it "calls the public lookup API, stores UUID in PluginStore and Discourse.cache" do
        expect(client).to receive(:get).with(
          "#{OpenNotes::PUBLIC_API_PREFIX}/community-servers/lookup",
          params: { platform: "discourse", platform_community_server_id: slug },
        ).and_return({ "data" => { "id" => uuid } })

        expect(described_class.community_server_uuid).to eq(uuid)
        expect(::PluginStore.get(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY)).to eq(uuid)
        expect(Discourse.cache.read(described_class::CACHE_KEY)).to eq(uuid)
      end

      it "returns nil and logs on API failure" do
        allow(client).to receive(:get).and_raise(OpenNotes::ApiError.new(500, "boom"))
        expect(Rails.logger).to receive(:warn).with(/lookup failed/i)
        expect(described_class.community_server_uuid).to be_nil
      end

      it "returns nil and logs on Faraday connection errors" do
        allow(client).to receive(:get).and_raise(Faraday::ConnectionFailed.new("nope"))
        expect(Rails.logger).to receive(:warn).with(/lookup failed/i)
        expect(described_class.community_server_uuid).to be_nil
      end

      it "returns nil without calling API when server_url is blank" do
        SiteSetting.opennotes_server_url = ""
        expect(OpenNotes::Client).not_to receive(:new)
        expect(Rails.logger).to receive(:warn).with(/missing server_url/i)
        expect(described_class.community_server_uuid).to be_nil
      end

      it "returns nil without calling API when api_key is blank" do
        SiteSetting.opennotes_api_key = ""
        expect(OpenNotes::Client).not_to receive(:new)
        expect(Rails.logger).to receive(:warn)
        expect(described_class.community_server_uuid).to be_nil
      end

      it "returns nil without calling API when platform_community_server_id is blank" do
        SiteSetting.opennotes_platform_community_server_id = ""
        expect(OpenNotes::Client).not_to receive(:new)
        expect(Rails.logger).to receive(:warn)
        expect(described_class.community_server_uuid).to be_nil
      end

      it "handles response with symbol keys" do
        allow(client).to receive(:get).and_return({ data: { id: uuid } })
        expect(described_class.community_server_uuid).to eq(uuid)
      end

      it "returns nil when response lacks a data.id field" do
        allow(client).to receive(:get).and_return({ "data" => {} })
        expect(described_class.community_server_uuid).to be_nil
        expect(::PluginStore.get(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY)).to be_nil
      end
    end
  end

  describe ".invalidate!" do
    it "clears both cache layers" do
      Discourse.cache.write(described_class::CACHE_KEY, uuid, expires_in: 5.minutes)
      ::PluginStore.set(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY, uuid)

      described_class.invalidate!

      expect(Discourse.cache.read(described_class::CACHE_KEY)).to be_nil
      expect(::PluginStore.get(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY)).to be_nil
    end
  end

  describe ".persist" do
    it "writes to both PluginStore and Discourse.cache" do
      described_class.persist(uuid)
      expect(::PluginStore.get(described_class::PLUGIN_NAMESPACE, described_class::PLUGIN_STORE_KEY)).to eq(uuid)
      expect(Discourse.cache.read(described_class::CACHE_KEY)).to eq(uuid)
    end
  end
end
