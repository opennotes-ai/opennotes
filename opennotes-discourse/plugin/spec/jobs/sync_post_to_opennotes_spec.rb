# frozen_string_literal: true

require "rails_helper"

RSpec.describe Jobs::SyncPostToOpennotes do
  fab!(:category)
  fab!(:topic) { Fabricate(:topic, category: category) }
  fab!(:post) { Fabricate(:post, topic: topic) }
  fab!(:user) { post.user }

  let(:client) { instance_double(OpenNotes::Client) }
  let(:community_server_id) { "test-community-server-id" }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"
    SiteSetting.opennotes_monitored_categories = category.slug

    PluginStore.set("discourse-opennotes", "community_server_id", community_server_id)

    allow(OpenNotes::Client).to receive(:new).and_return(client)
  end

  describe "#execute" do
    it "sends the post to the OpenNotes server" do
      captured_args = nil
      allow(client).to receive(:post) do |*args, **kwargs|
        captured_args = [args, kwargs]
        { "data" => { "id" => "req-1" } }
      end

      described_class.new.execute(post_id: post.id)

      expect(captured_args).not_to be_nil
      path, = captured_args[0]
      kwargs = captured_args[1]
      expect(path).to eq("/api/v2/requests")
      expect(kwargs[:body]).to include(
        data: include(
          type: "requests",
          attributes: include(
            platform_message_id: post.id.to_s,
            original_message_content: post.raw,
          ),
        ),
      )
    end

    it "skips when opennotes is disabled" do
      SiteSetting.opennotes_enabled = false
      allow(client).to receive(:post)

      described_class.new.execute(post_id: post.id)

      expect(client).not_to have_received(:post)
    end

    it "skips when post is in an unmonitored category" do
      SiteSetting.opennotes_monitored_categories = "other-category"
      allow(client).to receive(:post)

      described_class.new.execute(post_id: post.id)

      expect(client).not_to have_received(:post)
    end

    context "with subcategory slug paths" do
      fab!(:parent_category) { Fabricate(:category, slug: "parent") }
      fab!(:child_category) { Fabricate(:category, slug: "child", parent_category: parent_category) }
      fab!(:child_topic) { Fabricate(:topic, category: child_category) }
      fab!(:child_post) { Fabricate(:post, topic: child_topic) }

      it "matches subcategory by full slug path" do
        SiteSetting.opennotes_monitored_categories = "parent/child"
        allow(client).to receive(:post).and_return({ "data" => { "id" => "req-sub-1" } })

        described_class.new.execute(post_id: child_post.id)

        expect(client).to have_received(:post)
      end

      it "does not match subcategory by leaf slug alone" do
        SiteSetting.opennotes_monitored_categories = "child"
        allow(client).to receive(:post)

        described_class.new.execute(post_id: child_post.id)

        expect(client).not_to have_received(:post)
      end

      it "distinguishes ambiguous leaf slugs under different parents" do
        other_parent = Fabricate(:category, slug: "other-parent")
        other_child = Fabricate(:category, slug: "child", parent_category: other_parent)
        other_topic = Fabricate(:topic, category: other_child)
        other_post = Fabricate(:post, topic: other_topic)

        SiteSetting.opennotes_monitored_categories = "parent/child"
        allow(client).to receive(:post).and_return({ "data" => { "id" => "req-sub-2" } })

        described_class.new.execute(post_id: child_post.id)
        expect(client).to have_received(:post).once

        allow(client).to receive(:post)
        described_class.new.execute(post_id: other_post.id)
        expect(client).not_to have_received(:post)
      end
    end

    it "skips when post does not exist" do
      allow(client).to receive(:post)

      described_class.new.execute(post_id: -1)

      expect(client).not_to have_received(:post)
    end

    it "skips when community_server_id is not set" do
      PluginStore.remove("discourse-opennotes", "community_server_id")
      allow(client).to receive(:post)

      described_class.new.execute(post_id: post.id)

      expect(client).not_to have_received(:post)
    end

    it "skips scan-exempt posts" do
      post.custom_fields["opennotes_scan_exempt"] = true
      post.save_custom_fields
      allow(client).to receive(:post)

      described_class.new.execute(post_id: post.id)

      expect(client).not_to have_received(:post)
    end

    context "when server returns an auto_hide action" do
      let(:response) do
        {
          "data" => {
            "id" => "req-1",
            "attributes" => {
              "moderation_action" => "auto_hide",
              "note_id" => "note-1",
              "action_id" => "action-1",
            },
          },
        }
      end

      before { allow(client).to receive(:post).and_return(response) }

      it "hides the post" do
        described_class.new.execute(post_id: post.id)

        post.reload
        expect(post.hidden?).to eq(true)
      end

      it "creates a ReviewableOpennotesItem with auto_actioned state" do
        described_class.new.execute(post_id: post.id)

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id("req-1")
        expect(reviewable).to be_present
        expect(reviewable.opennotes_state).to eq("auto_actioned")
        expect(reviewable.opennotes_note_id).to eq("note-1")
        expect(reviewable.opennotes_action_id).to eq("action-1")
      end
    end

    context "when server returns a community_review action" do
      let(:response) do
        {
          "data" => {
            "id" => "req-2",
            "attributes" => {
              "moderation_action" => "community_review",
              "note_id" => "note-2",
            },
          },
        }
      end

      before { allow(client).to receive(:post).and_return(response) }

      it "creates a ReviewableOpennotesItem with pending state" do
        described_class.new.execute(post_id: post.id)

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id("req-2")
        expect(reviewable).to be_present
        expect(reviewable.opennotes_state).to eq("pending")
      end

      it "does not hide the post" do
        described_class.new.execute(post_id: post.id)

        post.reload
        expect(post.hidden?).to eq(false)
      end
    end
  end
end
