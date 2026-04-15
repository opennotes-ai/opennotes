# frozen_string_literal: true

require "rails_helper"

RSpec.describe Opennotes::WebhookController, type: :controller do
  routes { Discourse::Application.routes }

  let(:api_key) { "test-webhook-secret-key" }
  let(:post_record) { Fabricate(:post) }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_api_key = api_key
    post_record.custom_fields["opennotes_request_id"] = "req-uuid-1"
    post_record.custom_fields["opennotes_action_id"] = "act-uuid-1"
    post_record.save_custom_fields
  end

  def sign_payload(payload, secret = api_key)
    body = payload.to_json
    "sha256=" + OpenSSL::HMAC.hexdigest("SHA256", secret, body)
  end

  def send_webhook(payload, signature: nil)
    signature ||= sign_payload(payload)
    request.headers["X-Webhook-Signature"] = signature
    request.headers["CONTENT_TYPE"] = "application/json"
    post :receive, params: payload, as: :json
  end

  describe "HMAC verification" do
    it "rejects requests without a signature" do
      request.headers["CONTENT_TYPE"] = "application/json"
      post :receive, params: { event: "test" }, as: :json

      expect(response).to have_http_status(:unauthorized)
      expect(JSON.parse(response.body)["error"]).to eq("missing signature")
    end

    it "rejects requests with an invalid signature" do
      payload = { event: "moderation_action.proposed", action_id: "act-uuid-1" }
      send_webhook(payload, signature: "sha256=invalidsignature")

      expect(response).to have_http_status(:unauthorized)
      expect(JSON.parse(response.body)["error"]).to eq("invalid signature")
    end

    it "accepts requests with a valid signature" do
      payload = { event: "moderation_action.applied", action_id: "act-uuid-1" }
      send_webhook(payload)

      expect(response).to have_http_status(:ok)
      expect(JSON.parse(response.body)["received"]).to eq(true)
    end
  end

  describe "event routing" do
    it "handles moderation_action.proposed events" do
      expect_any_instance_of(described_class).to receive(:handle_action_proposed)
      payload = {
        event: "moderation_action.proposed",
        action_id: "act-uuid-new",
        request_id: "req-uuid-1",
        action_type: "hide_post",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "handles moderation_action.applied as no-op" do
      payload = { event: "moderation_action.applied", action_id: "act-uuid-1" }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "handles moderation_action.confirmed events" do
      expect_any_instance_of(described_class).to receive(:handle_action_confirmed)
      payload = {
        event: "moderation_action.confirmed",
        action_id: "act-uuid-1",
        note_id: "note-uuid-1",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "handles moderation_action.overturned events" do
      expect_any_instance_of(described_class).to receive(:handle_action_overturned)
      payload = {
        event: "moderation_action.overturned",
        action_id: "act-uuid-1",
        note_id: "note-uuid-1",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "handles moderation_action.dismissed events" do
      expect_any_instance_of(described_class).to receive(:handle_action_dismissed)
      payload = {
        event: "moderation_action.dismissed",
        action_id: "act-uuid-1",
        request_id: "req-uuid-1",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "handles note.status_changed events" do
      expect_any_instance_of(described_class).to receive(:handle_note_status_changed)
      payload = {
        event: "note.status_changed",
        note_id: "note-uuid-1",
        status: "CURRENTLY_RATED_HELPFUL",
        request_id: "req-uuid-1",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "logs unknown event types and returns ok" do
      payload = { event: "unknown.event_type" }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "reads event from event_type param when event is missing" do
      expect_any_instance_of(described_class).to receive(:handle_action_confirmed)
      payload = {
        event_type: "moderation_action.confirmed",
        action_id: "act-uuid-1",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end
  end

  describe "handle_action_proposed" do
    it "creates a ReviewableOpennotesItem and executes the action" do
      payload = {
        event: "moderation_action.proposed",
        action_id: "act-uuid-new",
        request_id: "req-uuid-1",
        action_type: "hide_post",
        classifier_evidence: { labels: { spam: true }, scores: { spam: 0.95 } },
      }

      captured_kwargs = nil
      allow(OpenNotes::ActionExecutor).to receive(:execute_action) do |**kwargs|
        captured_kwargs = kwargs
      end

      send_webhook(payload)
      expect(response).to have_http_status(:ok)

      expect(captured_kwargs).not_to be_nil
      expect(captured_kwargs[:action_type]).to eq("hide_post")
      expect(captured_kwargs[:post]).to eq(post_record)
    end

    it "creates a reviewable even without an action_type" do
      payload = {
        event: "moderation_action.proposed",
        action_id: "act-uuid-new",
        request_id: "req-uuid-1",
      }

      expect(OpenNotes::ActionExecutor).not_to receive(:execute_action)

      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end

    it "creates the reviewable in retro_review when an action_type is present" do
      payload = {
        event: "moderation_action.proposed",
        action_id: "act-uuid-new",
        request_id: "req-uuid-1",
        action_type: "hide_post",
      }

      allow(OpenNotes::ActionExecutor).to receive(:execute_action)

      send_webhook(payload)

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id("req-uuid-1")
      expect(reviewable).to be_present
      expect(reviewable.opennotes_state).to eq("retro_review")
    end

    it "creates the reviewable in under_review when no action_type is present" do
      payload = {
        event: "moderation_action.proposed",
        action_id: "act-uuid-new",
        request_id: "req-uuid-1",
      }

      send_webhook(payload)

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id("req-uuid-1")
      expect(reviewable).to be_present
      expect(reviewable.opennotes_state).to eq("under_review")
    end
  end

  describe "handle_action_dismissed" do
    [:pending, :under_review].each do |starting_state|
      context "when reviewable is in #{starting_state}" do
        let!(:reviewable_for_dismissal) do
          ReviewableOpennotesItem.create_for(
            post_record,
            state: starting_state,
            opennotes_request_id: "req-uuid-1",
            opennotes_action_id: "act-uuid-1",
          )
        end

        it "transitions to dismissed and sets ignored Discourse status" do
          payload = {
            event: "moderation_action.dismissed",
            action_id: "act-uuid-1",
            request_id: "req-uuid-1",
          }
          send_webhook(payload)

          reviewable_for_dismissal.reload
          expect(reviewable_for_dismissal.opennotes_state).to eq("dismissed")
          expect(reviewable_for_dismissal.status).to eq("ignored")
        end
      end
    end
  end

  describe "handle_action_confirmed" do
    let!(:reviewable_for_confirm) do
      r = ReviewableOpennotesItem.create_for(
        post_record,
        state: :auto_actioned,
        opennotes_request_id: "req-uuid-1",
        opennotes_action_id: "act-uuid-1",
      )
      r.transition_to(:retro_review)
      r
    end

    it "transitions a retro_review reviewable through action_confirmed to resolved" do
      payload = {
        event: "moderation_action.confirmed",
        action_id: "act-uuid-1",
        note_id: "note-uuid-1",
      }
      send_webhook(payload)

      expect(reviewable_for_confirm.reload.opennotes_state).to eq("resolved")
    end
  end

  describe "handle_action_overturned" do
    let!(:reviewable_for_overturn) do
      r = ReviewableOpennotesItem.create_for(
        post_record,
        state: :auto_actioned,
        opennotes_request_id: "req-uuid-1",
        opennotes_action_id: "act-uuid-1",
      )
      r.transition_to(:retro_review)
      r
    end

    it "unhides the post, sets scan exempt, adds annotation, and reaches restored" do
      expect(OpenNotes::ActionExecutor).to receive(:unhide_post)
      expect(OpenNotes::ActionExecutor).to receive(:set_scan_exempt)
      expect(OpenNotes::ActionExecutor).to receive(:add_staff_annotation)

      payload = {
        event: "moderation_action.overturned",
        action_id: "act-uuid-1",
        note_id: "note-uuid-1",
      }
      send_webhook(payload)
      expect(response).to have_http_status(:ok)
      expect(reviewable_for_overturn.reload.opennotes_state).to eq("restored")
    end
  end

  describe "handle_note_status_changed" do
    let!(:reviewable) do
      ReviewableOpennotesItem.create_for(
        post_record,
        state: :under_review,
        opennotes_request_id: "req-uuid-1",
      )
    end

    context "when status is CURRENTLY_RATED_HELPFUL and auto-hide is enabled" do
      before { SiteSetting.opennotes_auto_hide_on_consensus = true }

      it "hides the post" do
        expect(OpenNotes::ActionExecutor).to receive(:hide_post).with(post_record)

        payload = {
          event: "note.status_changed",
          note_id: "note-uuid-1",
          status: "CURRENTLY_RATED_HELPFUL",
          request_id: "req-uuid-1",
          recommended_action: "hide_post",
        }
        send_webhook(payload)
        expect(response).to have_http_status(:ok)
      end
    end

    context "when status is CURRENTLY_RATED_HELPFUL but auto-hide is disabled" do
      before { SiteSetting.opennotes_auto_hide_on_consensus = false }

      it "does not hide the post" do
        expect(OpenNotes::ActionExecutor).not_to receive(:hide_post)

        payload = {
          event: "note.status_changed",
          note_id: "note-uuid-1",
          status: "CURRENTLY_RATED_HELPFUL",
          request_id: "req-uuid-1",
          recommended_action: "hide_post",
        }
        send_webhook(payload)
        expect(response).to have_http_status(:ok)
      end
    end

    context "when status is CURRENTLY_RATED_NOT_HELPFUL" do
      it "transitions reviewable to consensus_not_helpful" do
        payload = {
          event: "note.status_changed",
          note_id: "note-uuid-1",
          status: "CURRENTLY_RATED_NOT_HELPFUL",
          request_id: "req-uuid-1",
        }
        send_webhook(payload)
        expect(response).to have_http_status(:ok)
      end
    end

    context "when reviewable is in retro_review" do
      let(:retro_post) { Fabricate(:post) }
      let!(:retro_reviewable) do
        r = ReviewableOpennotesItem.create_for(
          retro_post,
          state: :auto_actioned,
          opennotes_request_id: "req-uuid-retro",
        )
        r.transition_to(:retro_review)
        r
      end

      it "does not transition retro_review on CURRENTLY_RATED_HELPFUL (handled by polling job + moderation_action.confirmed)" do
        SiteSetting.opennotes_auto_hide_on_consensus = true
        allow(OpenNotes::ActionExecutor).to receive(:hide_post)

        payload = {
          event: "note.status_changed",
          note_id: "note-retro",
          status: "CURRENTLY_RATED_HELPFUL",
          request_id: "req-uuid-retro",
          recommended_action: "hide_post",
        }
        send_webhook(payload)

        expect(retro_reviewable.reload.opennotes_state).to eq("retro_review")
      end
    end
  end

  describe "idempotency" do
    it "returns ok for duplicate webhook delivery" do
      payload = { event: "moderation_action.applied", action_id: "act-uuid-1" }

      send_webhook(payload)
      expect(response).to have_http_status(:ok)

      send_webhook(payload)
      expect(response).to have_http_status(:ok)
    end
  end
end
