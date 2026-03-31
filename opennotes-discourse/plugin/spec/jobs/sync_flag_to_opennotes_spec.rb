# frozen_string_literal: true

require "rails_helper"

RSpec.describe Jobs::SyncFlagToOpennotes do
  fab!(:category)
  fab!(:topic) { Fabricate(:topic, category: category) }
  fab!(:post) { Fabricate(:post, topic: topic) }
  fab!(:flagger) { Fabricate(:user, trust_level: 2) }

  let(:client) { instance_double(OpenNotes::Client) }
  let(:community_server_id) { "test-community-server-id" }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"
    SiteSetting.opennotes_monitored_categories = category.slug
    SiteSetting.opennotes_route_flags_to_community = true

    PluginStore.set("discourse-opennotes", "community_server_id", community_server_id)

    allow(OpenNotes::Client).to receive(:new).and_return(client)
  end

  describe "#execute" do
    let(:args) do
      {
        post_id: post.id,
        flag_type: PostActionType.types[:inappropriate],
        flagged_by_id: flagger.id,
      }
    end

    it "sends the flag to the OpenNotes server" do
      allow(client).to receive(:post).and_return({ "data" => { "id" => "req-flag-1" } })

      described_class.new.execute(args)

      expect(client).to have_received(:post).with(
        "/api/v2/requests",
        body: hash_including(
          data: hash_including(
            type: "requests",
            attributes: hash_including(
              platform_message_id: post.id.to_s,
              metadata: hash_including(source: "user_flag"),
            ),
          ),
        ),
        user: flagger,
      )
    end

    it "creates a ReviewableOpennotesItem" do
      allow(client).to receive(:post).and_return(
        {
          "data" => {
            "id" => "req-flag-1",
            "attributes" => { "note_id" => "note-flag-1" },
          },
        },
      )

      described_class.new.execute(args)

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id("req-flag-1")
      expect(reviewable).to be_present
      expect(reviewable.opennotes_state).to eq("pending")
    end

    it "skips when opennotes is disabled" do
      SiteSetting.opennotes_enabled = false
      allow(client).to receive(:post)

      described_class.new.execute(args)

      expect(client).not_to have_received(:post)
    end

    it "skips when flag routing is disabled" do
      SiteSetting.opennotes_route_flags_to_community = false
      allow(client).to receive(:post)

      described_class.new.execute(args)

      expect(client).not_to have_received(:post)
    end

    it "skips when post does not exist" do
      allow(client).to receive(:post)

      described_class.new.execute(args.merge(post_id: -1))

      expect(client).not_to have_received(:post)
    end

    it "skips when flagger does not exist" do
      allow(client).to receive(:post)

      described_class.new.execute(args.merge(flagged_by_id: -1))

      expect(client).not_to have_received(:post)
    end

    it "skips when post is in an unmonitored category" do
      SiteSetting.opennotes_monitored_categories = "other-category"
      allow(client).to receive(:post)

      described_class.new.execute(args)

      expect(client).not_to have_received(:post)
    end

    it "skips when community_server_id is not set" do
      PluginStore.remove("discourse-opennotes", "community_server_id")
      allow(client).to receive(:post)

      described_class.new.execute(args)

      expect(client).not_to have_received(:post)
    end
  end
end
