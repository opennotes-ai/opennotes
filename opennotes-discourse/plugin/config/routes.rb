# frozen_string_literal: true

Discourse::Application.routes.append do
  post "/opennotes/webhooks/receive" => "opennotes/webhook#receive"

  scope "/admin/plugins/opennotes", constraints: StaffConstraint.new, defaults: { format: :json } do
    get "/dashboard" => "opennotes/admin#dashboard"
    get "/categories/:category_id/settings" => "opennotes/admin#category_settings"
    put "/categories/:category_id/settings" => "opennotes/admin#category_settings"
  end
end
