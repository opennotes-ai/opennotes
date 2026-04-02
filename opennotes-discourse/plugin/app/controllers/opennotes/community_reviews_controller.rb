# frozen_string_literal: true

module Opennotes
  class CommunityReviewsController < ::ApplicationController
    requires_plugin "discourse-opennotes"
    before_action :ensure_logged_in
    before_action :ensure_minimum_trust_level

    SCORE_FIELDS = %w[score scoring_status current_rating].freeze

    def index
      client = self.class.opennotes_client

      begin
        community_server = client.get("/api/v2/community-servers/lookup", params: {
          "platform" => "discourse",
          "platform_community_server_id" => Discourse.current_hostname,
        })
      rescue OpenNotes::ApiError => e
        return render json: { data: [] } if e.status == 404
        raise
      end

      server_id = community_server.dig("data", "id")
      return render json: { data: [] } unless server_id

      actions = client.get("/api/v2/moderation-actions", params: {
        "filter[community_server_id]" => server_id,
        "filter[action_state]" => "under_review",
      }, user: current_user)

      items = filter_by_review_group(actions["data"] || [], current_user)
      items = strip_score_fields(items) unless staff_user?
      render json: { data: items }
    rescue Faraday::Error => e
      render json: { data: [], error: I18n.t("opennotes.errors.server_unavailable") }, status: :ok
    rescue OpenNotes::ApiError => e
      render json: { data: [], error: I18n.t("opennotes.errors.server_unavailable") }, status: :ok
    end

    def show
      client = self.class.opennotes_client
      request_data = client.get("/api/v2/requests/#{params[:id]}", user: current_user)
      notes = client.get("/api/v2/notes", params: {
        "filter[request_id]" => params[:id],
      }, user: current_user)

      data = request_data["data"]
      included = notes["data"]

      unless staff_user?
        data = strip_score_fields_from_item(data) if data
        included = strip_score_fields(included) if included
      end

      render json: {
        data: data,
        included: included,
      }
    rescue Faraday::Error, OpenNotes::ApiError => e
      render json: { error: I18n.t("opennotes.errors.server_unavailable") }, status: :service_unavailable
    end

    def rate
      client = self.class.opennotes_client
      result = client.post("/api/v2/ratings", body: {
        data: {
          type: "ratings",
          attributes: {
            note_id: params[:note_id],
            helpfulness_level: params[:helpfulness_level],
          },
        },
      }, user: current_user)

      render json: result
    rescue OpenNotes::ApiError => e
      if e.status == 409
        render json: { error: I18n.t("opennotes.errors.already_voted") }, status: :conflict
      else
        render json: { error: I18n.t("opennotes.errors.server_unavailable") }, status: :service_unavailable
      end
    rescue Faraday::Error => e
      render json: { error: I18n.t("opennotes.errors.server_unavailable") }, status: :service_unavailable
    end

    private

    def ensure_minimum_trust_level
      return if current_user.admin? || current_user.moderator?

      min_tl = SiteSetting.opennotes_reviewer_min_trust_level
      raise Discourse::InvalidAccess unless current_user.trust_level >= min_tl
    end

    def staff_user?
      current_user.admin? || current_user.moderator?
    end

    def filter_by_review_group(items, user)
      is_staff = user.admin? || user.moderator?
      items.select do |item|
        review_group = item.dig("attributes", "review_group") || "staff"
        case review_group
        when "community" then is_staff || user.trust_level >= 2
        when "trusted" then is_staff || user.trust_level >= 3
        when "staff" then is_staff
        else is_staff
        end
      end
    end

    def strip_score_fields(items)
      return items unless items.is_a?(Array)
      items.map { |item| strip_score_fields_from_item(item) }
    end

    def strip_score_fields_from_item(item)
      return item unless item.is_a?(Hash) && item["attributes"].is_a?(Hash)
      item.merge("attributes" => item["attributes"].except(*SCORE_FIELDS))
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
