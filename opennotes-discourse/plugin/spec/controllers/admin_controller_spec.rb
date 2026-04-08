# frozen_string_literal: true

require "rails_helper"

RSpec.describe Opennotes::AdminController, type: :controller do
  routes { Discourse::Application.routes }

  let(:admin) { Fabricate(:admin) }
  let(:regular_user) { Fabricate(:user) }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "http://localhost:8000"
    SiteSetting.opennotes_api_key = "test-api-key"
    PluginStore.set("discourse-opennotes", "community_server_id", "cs-uuid-1")
  end

  describe "GET /admin/plugins/discourse-opennotes/dashboard" do
    context "when logged in as staff" do
      before { sign_in(admin) }

      it "returns JSON with scoring analysis data" do
        mock_client = instance_double(OpenNotes::Client)
        allow(OpenNotes::Client).to receive(:new).and_return(mock_client)
        allow(mock_client).to receive(:get).and_return({
          "activity" => { "total_posts" => 100 },
          "classification" => { "spam" => 10 },
          "consensus" => { "helpful" => 50 },
          "top_reviewers" => [],
        })

        get :dashboard, format: :json
        expect(response).to have_http_status(:ok)

        body = JSON.parse(response.body)
        expect(body).to have_key("activity")
        expect(body).to have_key("classification")
      end

      it "returns 404 when community server is not registered" do
        PluginStore.remove("discourse-opennotes", "community_server_id")

        get :dashboard, format: :json
        expect(response).to have_http_status(:not_found)

        body = JSON.parse(response.body)
        expect(body["error"]).to eq("Community server not registered")
      end

      it "returns 503 when opennotes server is unavailable" do
        mock_client = instance_double(OpenNotes::Client)
        allow(OpenNotes::Client).to receive(:new).and_return(mock_client)
        allow(mock_client).to receive(:get).and_raise(Faraday::ConnectionFailed.new("connection refused"))

        get :dashboard, format: :json
        expect(response).to have_http_status(:service_unavailable)
      end
    end

    context "when logged in as regular user" do
      before { sign_in(regular_user) }

      it "returns 403 forbidden" do
        get :dashboard, format: :json
        expect(response.status).to eq(404).or eq(403)
      end
    end

    context "when not logged in" do
      it "redirects or returns unauthorized" do
        get :dashboard, format: :json
        expect(response.status).to be_in([301, 302, 403, 404])
      end
    end
  end
end
