# frozen_string_literal: true

module Opennotes
  class AdminController < ::Admin::AdminController
    requires_plugin "discourse-opennotes"

    def dashboard
      platform_server_id = PluginStore.get("discourse-opennotes", "community_server_id")
      unless platform_server_id
        render json: { error: "Community server not registered" }, status: :not_found
        return
      end

      client = build_client
      lookup = client.get(
        "/api/v2/community-servers/lookup",
        params: { platform: "discourse", platform_community_server_id: platform_server_id },
      )
      server_uuid = lookup.dig("data", "id")
      unless server_uuid
        render json: { error: "Community server not found on OpenNotes" }, status: :not_found
        return
      end

      data = client.get("/api/v2/community-servers/#{server_uuid}/scoring-analysis")
      render json: data
    rescue OpenNotes::ApiError => e
      if e.status == 404
        render json: { activity: {}, classification: {}, consensus: {}, top_reviewers: [] }
      else
        render json: { error: e.message }, status: e.status
      end
    rescue Faraday::Error
      render json: { error: I18n.t("opennotes.errors.server_unavailable") }, status: :service_unavailable
    end

    def category_settings
      category_id = params.require(:category_id)
      category = Category.find(category_id)

      if request.get?
        settings = {
          category_id: category.id,
          enabled: category.custom_fields["opennotes_enabled"] == "true",
          auto_hide: category.custom_fields["opennotes_auto_hide"] == "true",
        }
        render json: settings
      elsif request.put?
        category.custom_fields["opennotes_enabled"] = params[:enabled].to_s
        category.custom_fields["opennotes_auto_hide"] = params[:auto_hide].to_s
        category.save_custom_fields

        render json: { success: true }
      end
    end

    private

    def build_client
      OpenNotes::Client.new(
        server_url: SiteSetting.opennotes_server_url,
        api_key: SiteSetting.opennotes_api_key,
      )
    end
  end
end
