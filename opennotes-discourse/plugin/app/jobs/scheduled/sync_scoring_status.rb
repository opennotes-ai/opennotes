# frozen_string_literal: true

module Jobs
  class SyncScoringStatus < ::Jobs::Scheduled
    every 5.minutes

    TERMINAL_STATES = %w[resolved restored dismissed].freeze
    PROCESSABLE_STATES = %w[under_review retro_review].freeze

    def execute(_args)
      return unless SiteSetting.opennotes_enabled

      community_server_id = PluginStore.get("discourse-opennotes", "community_server_id")
      return unless community_server_id

      last_poll = PluginStore.get("discourse-opennotes", "last_scoring_poll_at")
      last_poll ||= 30.minutes.ago.iso8601

      client = self.class.opennotes_client

      response = client.get(
        "/api/v2/requests",
        params: {
          "filter[status]" => "COMPLETED",
          "filter[requested_at__gte]" => last_poll,
          "filter[community_server_id]" => community_server_id,
        },
      )

      process_completed_requests(response, client)

      PluginStore.set("discourse-opennotes", "last_scoring_poll_at", Time.now.iso8601)
    rescue OpenNotes::ApiError => e
      Rails.logger.warn("OpenNotes scoring sync failed: #{e.message}")
    end

    private

    def process_completed_requests(response, client)
      requests = Array(response.is_a?(Hash) ? response["data"] : response)

      requests.each do |request_data|
        process_single_request(request_data, client)
      end
    end

    def process_single_request(request_data, client)
      request_id = request_data["id"]
      attrs = request_data["attributes"] || request_data
      platform_message_id = attrs["platform_message_id"]
      return unless platform_message_id

      post = Post.find_by(id: platform_message_id)
      return unless post

      reviewable = ReviewableOpennotesItem.find_by_opennotes_request_id(request_id)

      if reviewable
        sync_reviewable_state(reviewable, attrs, post, client)
      end
    end

    def sync_reviewable_state(reviewable, attrs, post, _client)
      note_status = attrs["note_status"] || attrs.dig("scoring", "status")
      return unless note_status

      ensure_reviewable_processable(reviewable, post)
      return unless reviewable.opennotes_state.in?(PROCESSABLE_STATES)

      recommended_action = attrs["recommended_action"]

      case note_status
      when "CURRENTLY_RATED_HELPFUL"
        handle_helpful_consensus(reviewable, post, recommended_action)
      when "CURRENTLY_RATED_NOT_HELPFUL"
        handle_not_helpful_consensus(reviewable, post)
      end
    end

    def ensure_reviewable_processable(reviewable, post)
      case reviewable.opennotes_state
      when "pending"
        warn_advance(reviewable, "pending", "under_review")
        reviewable.transition_to(:under_review)
      when "auto_actioned"
        warn_advance(reviewable, "auto_actioned", "retro_review")
        reviewable.transition_to(:retro_review)
      when "action_confirmed"
        warn_advance(reviewable, "action_confirmed", "resolved")
        reviewable.transition_to(:resolved)
      when "action_overturned"
        warn_advance(reviewable, "action_overturned", "restored")
        reviewable.transition_to(:restored)
      when "consensus_helpful"
        unless SiteSetting.opennotes_staff_approval_required
          warn_advance(reviewable, "consensus_helpful", "resolved")
          reviewable.transition_to(:resolved)
        end
      when "consensus_not_helpful"
        warn_advance(reviewable, "consensus_not_helpful", "resolved")
        reviewable.transition_to(:resolved)
      when "staff_overridden"
        warn_advance(reviewable, "staff_overridden", "resolved")
        reviewable.transition_to(:resolved)
      end
    end

    def warn_advance(reviewable, from_state, to_state)
      Rails.logger.warn(
        "[opennotes] Auto-advancing stranded reviewable #{reviewable.id} from #{from_state} to #{to_state}",
      )
    end

    def handle_helpful_consensus(reviewable, post, recommended_action)
      if reviewable.opennotes_state == "retro_review"
        reviewable.transition_to(:action_confirmed)
        reviewable.transition_to(:resolved)
      else
        reviewable.transition_to(:consensus_helpful)

        if SiteSetting.opennotes_auto_hide_on_consensus
          OpenNotes::ActionExecutor.hide_post(post)
        end

        unless SiteSetting.opennotes_staff_approval_required
          reviewable.transition_to(:resolved)
        end
      end
    end

    def handle_not_helpful_consensus(reviewable, post)
      if reviewable.opennotes_state == "retro_review"
        reviewable.transition_to(:action_overturned)
        OpenNotes::ActionExecutor.unhide_post(post)
        OpenNotes::ActionExecutor.set_scan_exempt(post, content_hash: Digest::SHA256.hexdigest(post.raw))
        OpenNotes::ActionExecutor.add_staff_annotation(
          post,
          text: I18n.t("opennotes.staff_annotations.action_overturned"),
        )
        reviewable.transition_to(:restored)
      else
        reviewable.transition_to(:consensus_not_helpful)
        reviewable.transition_to(:resolved)
      end
    end

    def self.opennotes_client
      OpenNotes::Client.new(
        server_url: SiteSetting.opennotes_server_url,
        api_key: SiteSetting.opennotes_api_key,
      )
    end
  end
end
