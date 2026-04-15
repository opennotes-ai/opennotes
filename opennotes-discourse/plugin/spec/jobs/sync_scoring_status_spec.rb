# frozen_string_literal: true

require "rails_helper"

RSpec.describe Jobs::SyncScoringStatus do
  fab!(:category)
  fab!(:topic) { Fabricate(:topic, category: category) }
  fab!(:post) { Fabricate(:post, topic: topic) }

  let(:client) { instance_double(OpenNotes::Client) }
  let(:community_server_id) { "test-community-server-id" }
  let(:request_id) { "req-1" }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"

    PluginStore.set("discourse-opennotes", "community_server_id", community_server_id)

    allow(described_class).to receive(:opennotes_client).and_return(client)
  end

  def stub_response(note_status:, recommended_action: nil)
    response = {
      "data" => [
        {
          "id" => request_id,
          "attributes" => {
            "platform_message_id" => post.id.to_s,
            "note_status" => note_status,
            "recommended_action" => recommended_action,
          }.compact,
        },
      ],
    }
    allow(client).to receive(:get).and_return(response)
  end

  def create_reviewable(state)
    ReviewableOpennotesItem.create_for(
      post,
      state: state,
      opennotes_request_id: request_id,
    )
  end

  describe "terminal-state guard" do
    described_class::TERMINAL_STATES.each do |terminal|
      it "skips reviewables already in #{terminal}" do
        reviewable = create_reviewable(:under_review)
        reviewable.opennotes_state = terminal
        reviewable.save!

        stub_response(note_status: "CURRENTLY_RATED_HELPFUL")

        expect { described_class.new.execute({}) }.not_to(
          change { reviewable.reload.opennotes_state },
        )
      end
    end
  end

  describe "auto-advance guard" do
    it "advances pending to under_review before processing consensus" do
      create_reviewable(:pending)
      stub_response(note_status: "CURRENTLY_RATED_NOT_HELPFUL")

      expect(Rails.logger).to receive(:warn).with(/pending to under_review/)

      described_class.new.execute({})

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
      expect(reviewable.opennotes_state).to eq("resolved")
    end

    it "advances auto_actioned to retro_review before processing consensus" do
      create_reviewable(:auto_actioned)
      stub_response(note_status: "CURRENTLY_RATED_HELPFUL")

      expect(Rails.logger).to receive(:warn).with(/auto_actioned to retro_review/)

      described_class.new.execute({})

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
      expect(reviewable.opennotes_state).to eq("resolved")
    end
  end

  describe "handle_helpful_consensus" do
    context "when reviewable is in retro_review" do
      before do
        reviewable = create_reviewable(:auto_actioned)
        reviewable.transition_to(:retro_review)
      end

      it "transitions through action_confirmed to resolved" do
        stub_response(note_status: "CURRENTLY_RATED_HELPFUL")

        described_class.new.execute({})

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
        expect(reviewable.opennotes_state).to eq("resolved")
      end
    end

    context "when reviewable is in under_review" do
      before { create_reviewable(:under_review) }

      it "auto-resolves when staff approval is not required" do
        SiteSetting.opennotes_staff_approval_required = false
        SiteSetting.opennotes_auto_hide_on_consensus = false
        stub_response(note_status: "CURRENTLY_RATED_HELPFUL")

        described_class.new.execute({})

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
        expect(reviewable.opennotes_state).to eq("resolved")
      end

      it "leaves item in consensus_helpful when staff approval required" do
        SiteSetting.opennotes_staff_approval_required = true
        SiteSetting.opennotes_auto_hide_on_consensus = false
        stub_response(note_status: "CURRENTLY_RATED_HELPFUL")

        described_class.new.execute({})

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
        expect(reviewable.opennotes_state).to eq("consensus_helpful")
      end

      it "hides the post when auto_hide_on_consensus is enabled" do
        SiteSetting.opennotes_staff_approval_required = false
        SiteSetting.opennotes_auto_hide_on_consensus = true
        expect(OpenNotes::ActionExecutor).to receive(:hide_post).with(post)

        stub_response(note_status: "CURRENTLY_RATED_HELPFUL")
        described_class.new.execute({})
      end
    end
  end

  describe "handle_not_helpful_consensus" do
    context "when reviewable is in retro_review" do
      before do
        reviewable = create_reviewable(:auto_actioned)
        reviewable.transition_to(:retro_review)
      end

      it "transitions through action_overturned to restored and unhides" do
        allow(OpenNotes::ActionExecutor).to receive(:unhide_post)
        allow(OpenNotes::ActionExecutor).to receive(:set_scan_exempt)
        allow(OpenNotes::ActionExecutor).to receive(:add_staff_annotation)

        stub_response(note_status: "CURRENTLY_RATED_NOT_HELPFUL")

        described_class.new.execute({})

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
        expect(reviewable.opennotes_state).to eq("restored")
        expect(OpenNotes::ActionExecutor).to have_received(:unhide_post).with(post)
      end
    end

    context "when reviewable is in under_review" do
      before { create_reviewable(:under_review) }

      it "transitions to consensus_not_helpful and resolves" do
        stub_response(note_status: "CURRENTLY_RATED_NOT_HELPFUL")

        described_class.new.execute({})

        reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
        expect(reviewable.opennotes_state).to eq("resolved")
      end
    end
  end

  describe "polling reentrancy" do
    it "is a no-op on a second run after consensus_helpful auto-resolved" do
      SiteSetting.opennotes_staff_approval_required = false
      SiteSetting.opennotes_auto_hide_on_consensus = false
      create_reviewable(:under_review)

      stub_response(note_status: "CURRENTLY_RATED_HELPFUL")
      described_class.new.execute({})
      described_class.new.execute({})

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
      expect(reviewable.opennotes_state).to eq("resolved")
    end
  end
end
