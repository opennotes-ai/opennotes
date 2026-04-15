# frozen_string_literal: true

module OpenNotes
  module StatusMapper
    module_function

    def display_status(reviewable)
      return nil unless reviewable

      raw_state = reviewable.opennotes_state
      consensus_type = reviewable.payload.is_a?(Hash) ? reviewable.payload["consensus_type"] : nil

      case raw_state
      when "consensus_helpful"
        "helpful"
      when "consensus_not_helpful"
        "not_helpful"
      when "resolved"
        consensus_type || "resolved"
      else
        raw_state
      end
    end
  end
end
