# frozen_string_literal: true

module Jobs
  class SyncScoringStatus < ::Jobs::Scheduled
    every 5.minutes

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
      return if reviewable.opennotes_state == "resolved"

      recommended_action = attrs["recommended_action"]

      case note_status
      when "CURRENTLY_RATED_HELPFUL"
        handle_helpful_consensus(reviewable, post, recommended_action)
      when "CURRENTLY_RATED_NOT_HELPFUL"
        handle_not_helpful_consensus(reviewable, post)
      end
    end

    def handle_helpful_consensus(reviewable, post, recommended_action)
      if reviewable.opennotes_state == "retro_review"
        reviewable.transition_to(:action_confirmed)
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
        jwt_secret: SiteSetting.opennotes_api_key,
      )
    end
  end
end
