# frozen_string_literal: true

Discourse::Application.routes.append do
  scope "/opennotes", defaults: { format: :json } do
    get "/reviews" => "opennotes/community_reviews#index"
    get "/reviews/:id" => "opennotes/community_reviews#show"
    post "/reviews/:note_id/rate" => "opennotes/community_reviews#rate"
  end
end
