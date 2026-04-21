# frozen_string_literal: true

module Opennotes
  class AdminController < ::Admin::AdminController
    requires_plugin "discourse-opennotes"

    def dashboard
      server_uuid = OpenNotes::CommunityServerResolver.community_server_id
      unless server_uuid
        render json: { error: "Community server not registered" }, status: :not_found
        return
      end

      # scoring-analysis lives on scoring_jsonapi_router, which is NOT in the
      # server's PUBLIC_ADAPTER_ROUTERS allowlist. Keep this one call on the
      # legacy /api/v2 prefix until scoring is audited and added to the allowlist.
      data = build_client.get("/api/v2/community-servers/#{server_uuid}/scoring-analysis")
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

    def register
      OpenNotes::CommunityServerResolver.invalidate!
      result = OpenNotes::PlatformRegistrar.register

      if result[:ok]
        render json: {
          success: true,
          community_server_uuid: result[:uuid],
          platform_community_server_id: result[:slug],
          name: result[:name],
        }
      else
        status =
          case result[:reason]
          when :missing_settings then :unprocessable_entity
          when :connection_error then :bad_gateway
          when :api_error then map_api_error_status(result[:status])
          else :bad_gateway
          end
        render json: {
          success: false,
          error: result[:message],
          reason: result[:reason],
          upstream_status: result[:status],
          community_server_uuid: result[:uuid],
        }.compact, status: status
      end
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

    def map_api_error_status(upstream_status)
      case upstream_status
      when 401, 403 then :unauthorized
      when 404 then :not_found
      when 400..499 then :bad_request
      else :bad_gateway
      end
    end

    def build_client
      OpenNotes::Client.new(
        server_url: SiteSetting.opennotes_server_url,
        api_key: SiteSetting.opennotes_api_key,
      )
    end
  end
end
