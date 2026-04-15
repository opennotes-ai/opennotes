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
      captured_args = nil
      allow(client).to receive(:post) do |*args, **kwargs|
        captured_args = [args, kwargs]
        { "data" => { "id" => "req-flag-1" } }
      end

      described_class.new.execute(args)

      expect(captured_args).not_to be_nil
      path, = captured_args[0]
      kwargs = captured_args[1]
      expect(path).to eq("/api/v2/requests")
      expect(kwargs[:user]).to eq(flagger)
      expect(kwargs[:body]).to include(
        data: include(
          type: "requests",
          attributes: include(
            platform_message_id: post.id.to_s,
            metadata: include(source: "user_flag"),
          ),
        ),
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
      expect(reviewable.opennotes_state).to eq("under_review")
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

      described_class.new.execute(args.merge(flagged_by_id: 999_999_999))

      expect(client).not_to have_received(:post)
    end

    it "skips when post is in an unmonitored category" do
      SiteSetting.opennotes_monitored_categories = "other-category"
      allow(client).to receive(:post)

      described_class.new.execute(args)

      expect(client).not_to have_received(:post)
    end

    context "with subcategory slug paths" do
      fab!(:parent_category) { Fabricate(:category, slug: "parent") }
      fab!(:child_category) { Fabricate(:category, slug: "child", parent_category: parent_category) }
      fab!(:child_topic) { Fabricate(:topic, category: child_category) }
      fab!(:child_post) { Fabricate(:post, topic: child_topic) }

      let(:child_args) do
        {
          post_id: child_post.id,
          flag_type: PostActionType.types[:inappropriate],
          flagged_by_id: flagger.id,
        }
      end

      it "matches subcategory by full slug path" do
        SiteSetting.opennotes_monitored_categories = "parent/child"
        allow(client).to receive(:post).and_return({ "data" => { "id" => "req-flag-sub-1" } })

        described_class.new.execute(child_args)

        expect(client).to have_received(:post)
      end

      it "does not match subcategory by leaf slug alone" do
        SiteSetting.opennotes_monitored_categories = "child"
        allow(client).to receive(:post)

        described_class.new.execute(child_args)

        expect(client).not_to have_received(:post)
      end
    end

    it "skips when community_server_id is not set" do
      PluginStore.remove("discourse-opennotes", "community_server_id")
      allow(client).to receive(:post)

      described_class.new.execute(args)

      expect(client).not_to have_received(:post)
    end
  end
end
