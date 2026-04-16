# frozen_string_literal: true

require "rails_helper"

RSpec.describe Opennotes::AdminController, type: :request do
  let(:admin) { Fabricate(:admin) }
  let(:regular_user) { Fabricate(:user) }
  let(:server_uuid) { "019d473a-0b2e-795b-b6a1-4919403313b8" }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "http://localhost:8000"
    SiteSetting.opennotes_api_key = "test-api-key"
    SiteSetting.opennotes_platform_community_server_id = "forum.example.com-abcd1234"
  end

  describe "GET /admin/plugins/discourse-opennotes/dashboard" do
    context "when logged in as staff" do
      before { sign_in(admin) }

      it "resolves UUID via CommunityServerResolver and returns scoring analysis" do
        allow(OpenNotes::CommunityServerResolver).to receive(:community_server_id).and_return(server_uuid)
        mock_client = instance_double(OpenNotes::Client)
        allow(OpenNotes::Client).to receive(:new).and_return(mock_client)
        allow(mock_client).to receive(:get)
          .with("/api/v2/community-servers/#{server_uuid}/scoring-analysis")
          .and_return({
            "activity" => { "total_posts" => 100 },
            "classification" => { "spam" => 10 },
            "consensus" => { "helpful" => 50 },
            "top_reviewers" => [],
          })

        get "/admin/plugins/discourse-opennotes/dashboard.json"
        expect(response).to have_http_status(:ok)

        body = response.parsed_body
        expect(body).to have_key("activity")
        expect(body).to have_key("classification")
      end

      it "returns 404 when resolver cannot obtain a UUID" do
        allow(OpenNotes::CommunityServerResolver).to receive(:community_server_id).and_return(nil)

        get "/admin/plugins/discourse-opennotes/dashboard.json"
        expect(response).to have_http_status(:not_found)

        body = response.parsed_body
        expect(body["error"]).to eq("Community server not registered")
      end

      it "does not call the server-side lookup endpoint directly" do
        allow(OpenNotes::CommunityServerResolver).to receive(:community_server_id).and_return(server_uuid)
        mock_client = instance_double(OpenNotes::Client)
        allow(OpenNotes::Client).to receive(:new).and_return(mock_client)
        expect(mock_client).not_to receive(:get).with("/api/v2/community-servers/lookup", any_args)
        allow(mock_client).to receive(:get)
          .with("/api/v2/community-servers/#{server_uuid}/scoring-analysis")
          .and_return({})

        get "/admin/plugins/discourse-opennotes/dashboard.json"
      end

      it "returns 503 when opennotes server is unavailable" do
        allow(OpenNotes::CommunityServerResolver).to receive(:community_server_id).and_return(server_uuid)
        mock_client = instance_double(OpenNotes::Client)
        allow(OpenNotes::Client).to receive(:new).and_return(mock_client)
        allow(mock_client).to receive(:get).and_raise(Faraday::ConnectionFailed.new("connection refused"))

        get "/admin/plugins/discourse-opennotes/dashboard.json"
        expect(response).to have_http_status(:service_unavailable)
      end
    end

    context "when logged in as regular user" do
      before { sign_in(regular_user) }

      it "returns 403 forbidden" do
        get "/admin/plugins/discourse-opennotes/dashboard.json"
        expect(response.status).to eq(404).or eq(403)
      end
    end

    context "when not logged in" do
      it "redirects or returns unauthorized" do
        get "/admin/plugins/discourse-opennotes/dashboard.json"
        expect(response.status).to be_in([301, 302, 403, 404])
      end
    end
  end
end
