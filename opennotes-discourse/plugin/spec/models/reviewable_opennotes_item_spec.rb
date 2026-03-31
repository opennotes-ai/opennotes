# frozen_string_literal: true

require "rails_helper"

RSpec.describe ReviewableOpennotesItem do
  fab!(:admin)
  fab!(:moderator)
  fab!(:category)
  fab!(:topic) { Fabricate(:topic, category: category) }
  fab!(:post) { Fabricate(:post, topic: topic) }

  let(:client) { instance_double(OpenNotes::Client) }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"

    allow(OpenNotes::Client).to receive(:new).and_return(client)
  end

  describe ".create_for" do
    it "creates a reviewable item for a post" do
      reviewable = described_class.create_for(
        post,
        state: :pending,
        opennotes_request_id: "req-1",
        opennotes_note_id: "note-1",
      )

      expect(reviewable).to be_persisted
      expect(reviewable.target).to eq(post)
      expect(reviewable.topic).to eq(post.topic)
      expect(reviewable.opennotes_state).to eq("pending")
      expect(reviewable.opennotes_request_id).to eq("req-1")
      expect(reviewable.opennotes_note_id).to eq("note-1")
    end

    it "creates with auto_actioned state and action_id" do
      reviewable = described_class.create_for(
        post,
        state: :auto_actioned,
        opennotes_request_id: "req-2",
        opennotes_note_id: "note-2",
        opennotes_action_id: "action-2",
      )

      expect(reviewable.opennotes_state).to eq("auto_actioned")
      expect(reviewable.opennotes_action_id).to eq("action-2")
    end
  end

  describe ".find_by_opennotes_request_id" do
    it "finds a reviewable by request ID" do
      created = described_class.create_for(
        post,
        state: :pending,
        opennotes_request_id: "req-lookup",
      )

      found = described_class.find_by_opennotes_request_id("req-lookup")
      expect(found).to eq(created)
    end

    it "returns nil when not found" do
      expect(described_class.find_by_opennotes_request_id("nonexistent")).to be_nil
    end
  end

  describe "#transition_to" do
    let(:reviewable) do
      described_class.create_for(
        post,
        state: :pending,
        opennotes_request_id: "req-transition",
      )
    end

    it "transitions from pending to under_review" do
      reviewable.transition_to(:under_review)
      expect(reviewable.opennotes_state).to eq("under_review")
    end

    it "transitions from pending to auto_actioned" do
      reviewable.transition_to(:auto_actioned)
      expect(reviewable.opennotes_state).to eq("auto_actioned")
    end

    it "transitions from pending to dismissed" do
      reviewable.transition_to(:dismissed)
      expect(reviewable.opennotes_state).to eq("dismissed")
    end

    it "raises on invalid transition" do
      expect { reviewable.transition_to(:resolved) }.to raise_error(
        described_class::InvalidStateTransition,
      )
    end

    it "follows the Tier 2 happy path" do
      reviewable.transition_to(:under_review)
      reviewable.transition_to(:consensus_helpful)
      reviewable.transition_to(:resolved)
      expect(reviewable.opennotes_state).to eq("resolved")
    end

    it "follows the Tier 1 happy path" do
      reviewable.transition_to(:auto_actioned)
      reviewable.transition_to(:retro_review)
      reviewable.transition_to(:action_confirmed)
      reviewable.transition_to(:resolved)
      expect(reviewable.opennotes_state).to eq("resolved")
    end

    it "follows the Tier 1 overturn path" do
      reviewable.transition_to(:auto_actioned)
      reviewable.transition_to(:retro_review)
      reviewable.transition_to(:action_overturned)
      reviewable.transition_to(:restored)
      expect(reviewable.opennotes_state).to eq("restored")
    end

    it "allows staff override from under_review" do
      reviewable.transition_to(:under_review)
      reviewable.transition_to(:staff_overridden)
      reviewable.transition_to(:resolved)
      expect(reviewable.opennotes_state).to eq("resolved")
    end
  end

  describe "#perform_agree" do
    let(:reviewable) do
      described_class.create_for(
        post,
        state: :under_review,
        opennotes_request_id: "req-agree",
        opennotes_note_id: "note-agree",
      )
    end

    it "force-publishes the note and hides the post" do
      allow(client).to receive(:post).and_return({})

      result = reviewable.perform_agree(moderator, nil)

      expect(result.success?).to eq(true)
      expect(client).to have_received(:post).with(
        "/api/v2/notes/note-agree/force-publish",
        body: {},
        user: moderator,
      )
      post.reload
      expect(post.hidden?).to eq(true)
      expect(reviewable.opennotes_state).to eq("resolved")
    end
  end

  describe "#perform_disagree" do
    let(:reviewable) do
      described_class.create_for(
        post,
        state: :under_review,
        opennotes_request_id: "req-disagree",
        opennotes_note_id: "note-disagree",
      )
    end

    before do
      post.hide!(PostActionType.types[:inappropriate])
    end

    it "dismisses the note and unhides the post" do
      allow(client).to receive(:post).and_return({})

      result = reviewable.perform_disagree(moderator, nil)

      expect(result.success?).to eq(true)
      expect(client).to have_received(:post).with(
        "/api/v2/notes/note-disagree/dismiss",
        body: {},
        user: moderator,
      )
      post.reload
      expect(post.hidden?).to eq(false)
      expect(reviewable.opennotes_state).to eq("resolved")
    end
  end

  describe "#perform_ignore" do
    let(:reviewable) do
      described_class.create_for(
        post,
        state: :pending,
        opennotes_request_id: "req-ignore",
      )
    end

    it "deletes the request on the server" do
      allow(client).to receive(:delete).and_return({})

      result = reviewable.perform_ignore(moderator, nil)

      expect(result.success?).to eq(true)
      expect(client).to have_received(:delete).with(
        "/api/v2/requests/req-ignore",
        user: moderator,
      )
      expect(reviewable.opennotes_state).to eq("dismissed")
    end
  end

  describe "#perform_escalate" do
    let(:reviewable) do
      described_class.create_for(
        post,
        state: :under_review,
        opennotes_request_id: "req-escalate",
      )
    end

    it "escalates the request on the server" do
      allow(client).to receive(:patch).and_return({})

      result = reviewable.perform_escalate(moderator, nil)

      expect(result.success?).to eq(true)
      expect(client).to have_received(:patch).with(
        "/api/v2/requests/req-escalate",
        body: { data: { attributes: { escalated: true } } },
        user: moderator,
      )
      expect(reviewable.opennotes_state).to eq("staff_overridden")
    end
  end
end
