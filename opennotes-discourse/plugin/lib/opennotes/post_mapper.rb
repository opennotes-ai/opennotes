# frozen_string_literal: true

module OpenNotes
  class PostMapper
    def self.to_request(post, community_server_id:)
      {
        data: {
          type: "requests",
          attributes: {
            request_id: "discourse-post-#{post.id}",
            requested_by: post.user.id.to_s,
            community_server_id: community_server_id,
            original_message_content: post.raw,
            platform_message_id: post.id.to_s,
            platform_channel_id: post.topic&.category&.id&.to_s,
            platform_author_id: post.user.id.to_s,
            platform_timestamp: post.created_at&.iso8601,
            metadata: build_metadata(post),
          },
        },
      }
    end

    def self.to_classification_payload(post)
      {
        content: post.raw,
        platform: "discourse",
        platform_message_id: post.id.to_s,
        metadata: build_metadata(post),
      }
    end

    def self.build_metadata(post)
      metadata = {
        title: post.topic&.title,
        category: post.topic&.category&.name,
        author_username: post.user&.username,
        author_trust_level: post.user&.trust_level,
        post_number: post.post_number,
        topic_id: post.topic_id,
      }
      metadata.compact
    end

    private_class_method :build_metadata
  end
end
