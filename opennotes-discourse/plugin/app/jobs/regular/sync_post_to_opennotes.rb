# frozen_string_literal: true

module Jobs
  class SyncPostToOpennotes < ::Jobs::Base
    sidekiq_options retry: 5

    def execute(args)
      post = Post.find_by(id: args[:post_id])
      return unless post
      return unless SiteSetting.opennotes_enabled
      return unless opennotes_monitored_category?(post.topic&.category)
      return if OpenNotes::ActionExecutor.scan_exempt?(post)

      client = self.class.opennotes_client
      community_server_id = PluginStore.get("discourse-opennotes", "community_server_id")
      return unless community_server_id

      payload = OpenNotes::PostMapper.to_request(post, community_server_id: community_server_id)
      response = client.post("/api/v2/requests", body: payload)

      handle_response(post, response, client)
    end

    private

    def handle_response(post, response, client)
      return unless response.is_a?(Hash)

      request_id = response.dig("data", "id") || response.dig("data", "attributes", "request_id")
      if request_id.present?
        post.custom_fields["opennotes_request_id"] = request_id
        post.save_custom_fields
      end

      request_data = response.dig("data", "attributes") || response.dig("data") || {}
      moderation_action = request_data["moderation_action"] || request_data["recommended_action"]

      if moderation_action == "auto_hide" || moderation_action == "immediate_action"
        handle_tier1_action(post, response)
      elsif moderation_action == "community_review"
        handle_tier2_action(post, response)
      end
    end

    def handle_tier1_action(post, response)
      request_id = response.dig("data", "id")
      note_id = response.dig("data", "attributes", "note_id") ||
                response.dig("data", "relationships", "note", "data", "id")
      action_id = response.dig("data", "attributes", "action_id") ||
                  response.dig("data", "relationships", "moderation_action", "data", "id")

      OpenNotes::ActionExecutor.hide_post(post, reason: :inappropriate)
      OpenNotes::ActionExecutor.add_staff_annotation(
        post,
        text: I18n.t("opennotes.staff_annotations.auto_hidden"),
      )

      ReviewableOpennotesItem.create_for(
        post,
        state: :auto_actioned,
        opennotes_request_id: request_id,
        opennotes_note_id: note_id,
        opennotes_action_id: action_id,
      )
    end

    def handle_tier2_action(post, response)
      request_id = response.dig("data", "id")
      note_id = response.dig("data", "attributes", "note_id") ||
                response.dig("data", "relationships", "note", "data", "id")

      ReviewableOpennotesItem.create_for(
        post,
        state: :pending,
        opennotes_request_id: request_id,
        opennotes_note_id: note_id,
      )
    end

    def opennotes_monitored_category?(category)
      return false unless category

      monitored = SiteSetting.opennotes_monitored_categories.to_s.split(",").map(&:strip)
      return true if monitored.empty?

      full_slug = category.slug_path.join("/")
      monitored.include?(full_slug) || monitored.include?(category.id.to_s)
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
