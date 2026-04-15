# frozen_string_literal: true

module Opennotes
  class WebhookController < ::ApplicationController
    requires_plugin "discourse-opennotes"
    skip_before_action :verify_authenticity_token
    skip_before_action :redirect_to_login_if_required
    before_action :verify_hmac_signature

    def receive
      event_type = params[:event] || params[:event_type]

      case event_type
      when "moderation_action.proposed"
        handle_action_proposed
      when "moderation_action.applied"
        :noop
      when "moderation_action.confirmed"
        handle_action_confirmed
      when "moderation_action.overturned"
        handle_action_overturned
      when "moderation_action.dismissed"
        handle_action_dismissed
      when "note.status_changed"
        handle_note_status_changed
      else
        Rails.logger.warn("[opennotes] Unknown webhook event: #{event_type}")
      end

      render json: { received: true }, status: :ok
    end

    private

    def verify_hmac_signature
      signature = request.headers["X-Webhook-Signature"]
      unless signature.present?
        render json: { error: "missing signature" }, status: :unauthorized
        return
      end

      body = request.body.read
      request.body.rewind
      secret = SiteSetting.opennotes_api_key
      expected = "sha256=" + OpenSSL::HMAC.hexdigest("SHA256", secret, body)

      unless ActiveSupport::SecurityUtils.secure_compare(expected, signature)
        render json: { error: "invalid signature" }, status: :unauthorized
      end
    end

    def handle_action_proposed
      action_id = params[:action_id]
      request_id = params[:request_id]
      action_type = params[:action_type] || params[:recommended_action]

      post = find_post_by_request_id(request_id)
      return unless post

      reviewable = find_or_create_reviewable(
        post,
        request_id: request_id,
        action_id: action_id,
        state: :under_review,
      )

      if action_type.present?
        OpenNotes::ActionExecutor.execute_action(
          action_type: action_type,
          post: post,
          metadata: {
            action_id: action_id,
            classifier_evidence: params[:classifier_evidence],
            review_group: params[:review_group],
          },
        )
      end

      reviewable
    end

    def handle_action_confirmed
      action_id = params[:action_id]
      reviewable = find_reviewable_by_action_id(action_id)
      return unless reviewable

      if reviewable.opennotes_state.to_sym == :retro_review
        reviewable.transition_to(:action_confirmed)
        reviewable.transition_to(:resolved)
      end
    end

    def handle_action_overturned
      action_id = params[:action_id]
      reviewable = find_reviewable_by_action_id(action_id)
      return unless reviewable

      post = reviewable.target
      return unless post

      OpenNotes::ActionExecutor.unhide_post(post)

      content_hash = Digest::SHA256.hexdigest(post.raw)
      OpenNotes::ActionExecutor.set_scan_exempt(post, content_hash: content_hash)

      OpenNotes::ActionExecutor.add_staff_annotation(
        post,
        text: I18n.t("opennotes.staff_annotation.overturned"),
      )

      if reviewable.opennotes_state.to_sym == :retro_review
        reviewable.transition_to(:action_overturned)
        reviewable.transition_to(:restored)
      end
    end

    def handle_action_dismissed
      action_id = params[:action_id]
      request_id = params[:request_id]

      reviewable = find_reviewable_by_action_id(action_id)
      reviewable ||= ReviewableOpennotesItem.find_by_opennotes_request_id(request_id) if request_id.present?
      return unless reviewable

      if reviewable.opennotes_state.to_sym == :pending
        reviewable.transition_to(:dismissed)
      elsif reviewable.opennotes_state.to_sym == :under_review
        reviewable.opennotes_state = "dismissed"
        reviewable.status = Reviewable.statuses[:ignored]
        reviewable.save!
      end
    end

    def handle_note_status_changed
      note_status = params[:status]
      request_id = params[:request_id]
      recommended_action = params[:recommended_action]

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
      return unless reviewable

      post = reviewable.target
      return unless post

      case note_status
      when "CURRENTLY_RATED_HELPFUL"
        if recommended_action == "hide_post" && SiteSetting.opennotes_auto_hide_on_consensus
          OpenNotes::ActionExecutor.hide_post(post)
          if reviewable.opennotes_state.to_sym == :under_review
            reviewable.transition_to(:consensus_helpful)
            reviewable.transition_to(:resolved)
          end
        end
      when "CURRENTLY_RATED_NOT_HELPFUL"
        if reviewable.opennotes_state.to_sym == :under_review
          reviewable.transition_to(:consensus_not_helpful)
          reviewable.transition_to(:resolved)
        end
      end
    end

    def find_post_by_request_id(request_id)
      return nil unless request_id.present?
      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
      return reviewable.target if reviewable

      custom_field = PostCustomField.find_by(name: "opennotes_request_id", value: request_id)
      custom_field&.post
    end

    def find_reviewable_by_action_id(action_id)
      return nil unless action_id.present?
      ReviewableOpennotesItem.where("payload->>'opennotes_action_id' = ?", action_id).first
    end

    def find_or_create_reviewable(post, request_id:, action_id:, state: :under_review)
      existing = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)
      return existing if existing

      post.custom_fields["opennotes_request_id"] = request_id
      post.custom_fields["opennotes_action_id"] = action_id if action_id.present?
      post.save_custom_fields

      ReviewableOpennotesItem.create_for(
        post,
        state: state,
        opennotes_request_id: request_id,
        opennotes_action_id: action_id,
      )
    end
  end
end
