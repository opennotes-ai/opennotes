# frozen_string_literal: true

module Opennotes
  class AdminController < ::Admin::AdminController
    requires_plugin "discourse-opennotes"

    def dashboard
      client = build_client
      data = client.get("/api/v1/scoring/analysis")
      render json: data
    rescue OpenNotes::ApiError => e
      render json: { error: e.message }, status: e.status
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
        jwt_secret: SiteSetting.opennotes_api_key,
      )
    end
  end
end
