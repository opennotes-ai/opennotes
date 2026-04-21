# frozen_string_literal: true

module Jobs
  class SyncFlagToOpennotes < ::Jobs::Base
    sidekiq_options retry: 5

    def execute(args)
      return unless SiteSetting.opennotes_enabled
      return unless SiteSetting.opennotes_route_flags_to_community

      post = Post.find_by(id: args[:post_id])
      return unless post
      return unless opennotes_monitored_category?(post.topic&.category)

      flag_type = args[:flag_type]
      flagged_by_id = args[:flagged_by_id]
      flagged_by = User.find_by(id: flagged_by_id)
      return unless flagged_by

      platform_community_server_id = SiteSetting.opennotes_platform_community_server_id
      return if platform_community_server_id.blank?

      client = self.class.opennotes_client

      payload =
        build_flag_payload(post, platform_community_server_id, flag_type, flagged_by)
      response = client.post("#{OpenNotes::PUBLIC_API_PREFIX}/requests", body: payload, user: flagged_by)

      handle_response(post, response)
    end

    private

    def build_flag_payload(post, community_server_id, flag_type, flagged_by)
      {
        data: {
          type: "requests",
          attributes: {
            request_id: "discourse-flag-#{post.id}-#{Time.now.to_i}",
            requested_by: flagged_by.id.to_s,
            community_server_id: community_server_id,
            original_message_content: post.raw,
            platform_message_id: post.id.to_s,
            platform_channel_id: post.topic&.category&.id&.to_s,
            platform_author_id: post.user.id.to_s,
            platform_timestamp: post.created_at&.iso8601,
            metadata: OpenNotes::PostMapper.to_classification_payload(post)[:metadata].merge(
              flag_type: flag_type,
              flagged_by_username: flagged_by.username,
              flagged_by_trust_level: flagged_by.trust_level,
              source: "user_flag",
            ),
          },
        },
      }
    end

    def handle_response(post, response)
      return unless response.is_a?(Hash)

      request_id = response.dig("data", "id")
      note_id = response.dig("data", "attributes", "note_id") ||
                response.dig("data", "relationships", "note", "data", "id")

      ReviewableOpennotesItem.create_for(
        post,
        state: :under_review,
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
      )
    end
  end
end
