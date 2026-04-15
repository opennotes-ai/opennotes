# frozen_string_literal: true

require "rails_helper"

RSpec.describe OpenNotes::StatusMapper do
  describe ".display_status" do
    it "returns nil for a nil reviewable" do
      expect(described_class.display_status(nil)).to be_nil
    end

    it "maps consensus_helpful to helpful" do
      reviewable = double(opennotes_state: "consensus_helpful", payload: {})
      expect(described_class.display_status(reviewable)).to eq("helpful")
    end

    it "maps consensus_not_helpful to not_helpful" do
      reviewable = double(opennotes_state: "consensus_not_helpful", payload: {})
      expect(described_class.display_status(reviewable)).to eq("not_helpful")
    end

    it "maps resolved with consensus_type=helpful to helpful" do
      reviewable = double(
        opennotes_state: "resolved",
        payload: { "consensus_type" => "helpful" },
      )
      expect(described_class.display_status(reviewable)).to eq("helpful")
    end

    it "maps resolved with consensus_type=not_helpful to not_helpful" do
      reviewable = double(
        opennotes_state: "resolved",
        payload: { "consensus_type" => "not_helpful" },
      )
      expect(described_class.display_status(reviewable)).to eq("not_helpful")
    end

    it "returns 'resolved' for resolved with no consensus_type (staff override path)" do
      reviewable = double(opennotes_state: "resolved", payload: {})
      expect(described_class.display_status(reviewable)).to eq("resolved")
    end

    it "passes through non-consensus, non-resolved states verbatim" do
      %w[pending under_review auto_actioned retro_review action_confirmed
         action_overturned staff_overridden restored dismissed].each do |state|
        reviewable = double(opennotes_state: state, payload: {})
        expect(described_class.display_status(reviewable)).to eq(state)
      end
    end

    it "tolerates a non-Hash payload" do
      reviewable = double(opennotes_state: "resolved", payload: nil)
      expect(described_class.display_status(reviewable)).to eq("resolved")
    end
  end
end
