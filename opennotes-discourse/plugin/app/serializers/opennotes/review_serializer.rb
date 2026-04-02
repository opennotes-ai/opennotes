# frozen_string_literal: true

module OpenNotes
  class ReviewSerializer < ApplicationSerializer
    attributes :id,
               :opennotes_request_id,
               :opennotes_note_id,
               :opennotes_action_id,
               :opennotes_state,
               :post_id,
               :topic_id,
               :category_id,
               :post_content,
               :post_author,
               :created_at,
               :updated_at

    def opennotes_request_id
      object.opennotes_request_id
    end

    def opennotes_note_id
      object.opennotes_note_id
    end

    def opennotes_action_id
      object.opennotes_action_id
    end

    def opennotes_state
      object.opennotes_state
    end

    def post_id
      object.target_id
    end

    def topic_id
      object.topic_id
    end

    def category_id
      object.target&.topic&.category_id
    end

    def post_content
      object.target&.raw
    end

    def post_author
      user = object.target&.user
      return unless user

      {
        id: user.id,
        username: user.username,
        avatar_url: user.avatar_template_url,
        trust_level: user.trust_level,
      }
    end
  end
end
