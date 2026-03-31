# frozen_string_literal: true

module OpenNotes
  class ActionExecutor
    SCAN_EXEMPT_FIELD = "opennotes_scan_exempt"
    SCAN_EXEMPT_HASH_FIELD = "opennotes_scan_exempt_hash"

    def self.execute_action(action_type:, post:, metadata: {})
      case action_type.to_s
      when "hide_post"
        hide_post(post, reason: metadata[:reason] || :spam)
      when "unhide_post"
        unhide_post(post)
      when "add_staff_annotation"
        add_staff_annotation(post, text: metadata[:text])
      when "set_scan_exempt"
        set_scan_exempt(post, content_hash: metadata[:content_hash])
      when "clear_scan_exempt"
        clear_scan_exempt(post)
      else
        Rails.logger.warn("[opennotes] Unknown action type: #{action_type}")
      end
    end

    def self.hide_post(post, reason: :spam)
      return if post.hidden?

      post_action_type = resolve_post_action_type(reason)
      PostAction.act(Discourse.system_user, post, post_action_type)
    end

    def self.unhide_post(post)
      return unless post.hidden?

      post.unhide!
      PostAction.remove_act(Discourse.system_user, post, PostActionType.types[:spam])
    rescue StandardError => e
      Rails.logger.warn("[opennotes] Error removing post action during unhide: #{e.message}")
    end

    def self.add_staff_annotation(post, text:)
      return unless text.present?

      post.topic.add_moderator_post(
        Discourse.system_user,
        text,
        post_type: Post.types[:whisper],
      )
    end

    def self.set_scan_exempt(post, content_hash:)
      post.custom_fields[SCAN_EXEMPT_FIELD] = true
      post.custom_fields[SCAN_EXEMPT_HASH_FIELD] = content_hash
      post.save_custom_fields
    end

    def self.clear_scan_exempt(post)
      post.custom_fields.delete(SCAN_EXEMPT_FIELD)
      post.custom_fields.delete(SCAN_EXEMPT_HASH_FIELD)
      post.save_custom_fields
    end

    def self.scan_exempt?(post)
      post.custom_fields[SCAN_EXEMPT_FIELD].present?
    end

    def self.scan_exempt_hash(post)
      post.custom_fields[SCAN_EXEMPT_HASH_FIELD]
    end

    def self.resolve_post_action_type(reason)
      case reason.to_sym
      when :spam
        PostActionType.types[:spam]
      when :inappropriate
        PostActionType.types[:inappropriate]
      when :off_topic
        PostActionType.types[:off_topic]
      else
        PostActionType.types[:spam]
      end
    end
    private_class_method :resolve_post_action_type
  end
end
