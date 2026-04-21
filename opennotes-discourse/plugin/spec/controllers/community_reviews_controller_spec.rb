# frozen_string_literal: true

require "rails_helper"

RSpec.describe Opennotes::CommunityReviewsController, type: :request do
  fab!(:admin) { Fabricate(:admin) }
  fab!(:moderator) { Fabricate(:moderator) }
  fab!(:tl3_user) { Fabricate(:trust_level_3) }
  fab!(:tl2_user) { Fabricate(:trust_level_2) }
  fab!(:tl1_user) { Fabricate(:trust_level_1) }
  fab!(:tl0_user) { Fabricate(:user, trust_level: 0) }

  let(:server_url) { "https://opennotes.test" }
  let(:api_key) { "test-api-key" }
  let(:server_uuid) { "server-123" }
  let(:mock_client) { double("OpenNotes::Client") }

  let(:community_item) do
    {
      "id" => "action-1",
      "type" => "moderation-actions",
      "attributes" => {
        "review_group" => "community",
        "action_state" => "under_review",
        "score" => 0.75,
        "scoring_status" => "pending",
        "current_rating" => "helpful",
      },
    }
  end

  let(:trusted_item) do
    {
      "id" => "action-2",
      "type" => "moderation-actions",
      "attributes" => {
        "review_group" => "trusted",
        "action_state" => "under_review",
      },
    }
  end

  let(:staff_item) do
    {
      "id" => "action-3",
      "type" => "moderation-actions",
      "attributes" => {
        "review_group" => "staff",
        "action_state" => "under_review",
      },
    }
  end

  let(:actions_response) do
    { "data" => [community_item, trusted_item, staff_item] }
  end

  def stub_client_index(resolver_uuid: server_uuid, actions: actions_response)
    allow(OpenNotes::CommunityServerResolver).to receive(:community_server_uuid).and_return(resolver_uuid)
    allow(mock_client).to receive(:get) do |path, **_kwargs|
      case path
      when "#{OpenNotes::PUBLIC_API_PREFIX}/moderation-actions"
        actions
      else
        raise "Unexpected get call: #{path}"
      end
    end
  end

  def stub_client_show(request_data:, notes_data:)
    allow(mock_client).to receive(:get) do |path, **_kwargs|
      if path.start_with?("#{OpenNotes::PUBLIC_API_PREFIX}/requests/")
        request_data
      elsif path == "#{OpenNotes::PUBLIC_API_PREFIX}/notes"
        notes_data
      else
        raise "Unexpected get call: #{path}"
      end
    end
  end

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = server_url
    SiteSetting.opennotes_api_key = api_key
    SiteSetting.opennotes_reviewer_min_trust_level = 2

    allow(Opennotes::CommunityReviewsController).to receive(:opennotes_client).and_return(mock_client)
  end

  describe "GET /opennotes/reviews" do
    context "when user is not logged in" do
      it "returns 403" do
        get "/opennotes/reviews.json"
        expect(response.status).to eq(403)
      end
    end

    context "when user is TL0" do
      before { sign_in(tl0_user) }

      it "returns 403 due to trust level gating" do
        get "/opennotes/reviews.json"
        expect(response.status).to eq(403)
      end
    end

    context "when user is TL1" do
      before { sign_in(tl1_user) }

      it "returns 403 due to trust level gating" do
        get "/opennotes/reviews.json"
        expect(response.status).to eq(403)
      end
    end

    context "when user is TL2" do
      before { sign_in(tl2_user) }

      it "returns pending items filtered by review group" do
        stub_client_index

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        ids = json["data"].map { |item| item["id"] }
        expect(ids).to include("action-1")
        expect(ids).not_to include("action-2")
        expect(ids).not_to include("action-3")
      end

      it "strips score fields for non-staff users" do
        stub_client_index

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        item = json["data"].find { |i| i["id"] == "action-1" }
        expect(item["attributes"]).not_to have_key("score")
        expect(item["attributes"]).not_to have_key("scoring_status")
        expect(item["attributes"]).not_to have_key("current_rating")
      end

      it "returns empty data when resolver returns no UUID" do
        stub_client_index(resolver_uuid: nil)

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)
        expect(response.parsed_body["data"]).to eq([])
      end
    end

    context "when user is TL3" do
      before { sign_in(tl3_user) }

      it "sees community and trusted items but not staff items" do
        stub_client_index

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        ids = json["data"].map { |item| item["id"] }
        expect(ids).to include("action-1", "action-2")
        expect(ids).not_to include("action-3")
      end
    end

    context "when user is admin" do
      before { sign_in(admin) }

      it "sees all items including staff-only" do
        stub_client_index

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        ids = json["data"].map { |item| item["id"] }
        expect(ids).to include("action-1", "action-2", "action-3")
      end

      it "preserves score fields for staff users" do
        stub_client_index

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        item = json["data"].find { |i| i["id"] == "action-1" }
        expect(item["attributes"]).to have_key("score")
        expect(item["attributes"]).to have_key("scoring_status")
        expect(item["attributes"]).to have_key("current_rating")
      end
    end

    context "when user is moderator" do
      before { sign_in(moderator) }

      it "sees all items including staff-only" do
        stub_client_index

        get "/opennotes/reviews.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        ids = json["data"].map { |item| item["id"] }
        expect(ids).to include("action-1", "action-2", "action-3")
      end
    end
  end

  describe "GET /opennotes/reviews/:id" do
    let(:request_response) do
      {
        "data" => {
          "id" => "req-1",
          "type" => "requests",
          "attributes" => {
            "status" => "pending",
            "score" => 0.8,
            "scoring_status" => "active",
          },
        },
      }
    end

    let(:notes_response) do
      {
        "data" => [
          {
            "id" => "note-1",
            "type" => "notes",
            "attributes" => {
              "content" => "This post needs context",
              "current_rating" => "helpful",
            },
          },
        ],
      }
    end

    context "when user is TL2" do
      before { sign_in(tl2_user) }

      it "returns request data with notes" do
        stub_client_show(request_data: request_response, notes_data: notes_response)

        get "/opennotes/reviews/req-1.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        expect(json["data"]["id"]).to eq("req-1")
        expect(json["included"].length).to eq(1)
      end

      it "strips score fields from response" do
        stub_client_show(request_data: request_response, notes_data: notes_response)

        get "/opennotes/reviews/req-1.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        expect(json["data"]["attributes"]).not_to have_key("score")
        expect(json["data"]["attributes"]).not_to have_key("scoring_status")
        expect(json["included"][0]["attributes"]).not_to have_key("current_rating")
      end
    end

    context "when user is admin" do
      before { sign_in(admin) }

      it "preserves score fields for staff" do
        stub_client_show(request_data: request_response, notes_data: notes_response)

        get "/opennotes/reviews/req-1.json"
        expect(response.status).to eq(200)

        json = response.parsed_body
        expect(json["data"]["attributes"]).to have_key("score")
        expect(json["included"][0]["attributes"]).to have_key("current_rating")
      end
    end
  end

  describe "POST /opennotes/reviews/:note_id/rate" do
    context "when user is TL2" do
      before { sign_in(tl2_user) }

      it "proxies rating to server" do
        allow(mock_client).to receive(:post).and_return(
          { "data" => { "id" => "rating-1", "type" => "ratings" } },
        )

        post "/opennotes/reviews/note-1/rate.json", params: { helpfulness_level: "helpful" }
        expect(response.status).to eq(200)

        json = response.parsed_body
        expect(json["data"]["id"]).to eq("rating-1")
      end

      it "returns 409 for duplicate vote" do
        allow(mock_client).to receive(:post).and_raise(
          OpenNotes::ApiError.new(409, { "error" => "duplicate" }),
        )

        post "/opennotes/reviews/note-1/rate.json", params: { helpfulness_level: "helpful" }
        expect(response.status).to eq(409)

        json = response.parsed_body
        expect(json["error"]).to be_present
      end

      it "returns 503 for non-409 API errors" do
        allow(mock_client).to receive(:post).and_raise(
          OpenNotes::ApiError.new(500, { "error" => "server error" }),
        )

        post "/opennotes/reviews/note-1/rate.json", params: { helpfulness_level: "helpful" }
        expect(response.status).to eq(503)
      end
    end

    context "when user is TL0" do
      before { sign_in(tl0_user) }

      it "returns 403 due to trust level gating" do
        post "/opennotes/reviews/note-1/rate.json", params: { helpfulness_level: "helpful" }
        expect(response.status).to eq(403)
      end
    end
  end

  describe "review group filtering" do
    before { sign_in(tl2_user) }

    it "defaults unknown review groups to staff-only" do
      unknown_group_item = {
        "id" => "action-unknown",
        "type" => "moderation-actions",
        "attributes" => {
          "review_group" => "unknown_group",
          "action_state" => "under_review",
        },
      }

      stub_client_index(actions: { "data" => [unknown_group_item] })

      get "/opennotes/reviews.json"
      expect(response.status).to eq(200)

      json = response.parsed_body
      expect(json["data"]).to be_empty
    end

    it "defaults missing review group to staff-only" do
      no_group_item = {
        "id" => "action-no-group",
        "type" => "moderation-actions",
        "attributes" => {
          "action_state" => "under_review",
        },
      }

      stub_client_index(actions: { "data" => [no_group_item] })

      get "/opennotes/reviews.json"
      expect(response.status).to eq(200)

      json = response.parsed_body
      expect(json["data"]).to be_empty
    end
  end

  describe "configurable minimum trust level" do
    it "respects custom minimum trust level setting" do
      SiteSetting.opennotes_reviewer_min_trust_level = 3
      sign_in(tl2_user)

      get "/opennotes/reviews.json"
      expect(response.status).to eq(403)
    end

    it "allows access when trust level meets custom threshold" do
      SiteSetting.opennotes_reviewer_min_trust_level = 3
      sign_in(tl3_user)

      stub_client_index(actions: { "data" => [community_item] })

      get "/opennotes/reviews.json"
      expect(response.status).to eq(200)
    end
  end
end
