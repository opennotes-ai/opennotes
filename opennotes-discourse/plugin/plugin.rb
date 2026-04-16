# frozen_string_literal: true

# name: discourse-opennotes
# about: Open Notes - Moderation — community-driven context notes with consensus scoring
# version: 0.1.0
# authors: Open Notes
# url: https://github.com/opennotes-ai/discourse-opennotes
# required_version: 3.2.0

enabled_site_setting :opennotes_enabled

register_asset "stylesheets/opennotes.scss"

after_initialize do
  %w[client user_mapper post_mapper action_executor status_mapper slug_generator community_server_resolver platform_registrar].each do |f|
    load File.expand_path("../lib/opennotes/#{f}.rb", __FILE__)
  end

  if SiteSetting.opennotes_platform_community_server_id.blank?
    SiteSetting.opennotes_platform_community_server_id = OpenNotes::SlugGenerator.generate_for_site
  end

  %w[
    app/jobs/regular/sync_post_to_opennotes
    app/jobs/regular/sync_flag_to_opennotes
    app/jobs/scheduled/sync_scoring_status
    app/models/reviewable_opennotes_item
    app/serializers/opennotes/review_serializer
    app/controllers/opennotes/admin_controller
    app/controllers/opennotes/community_reviews_controller
    app/controllers/opennotes/webhook_controller
  ].each { |f| load File.expand_path("../#{f}.rb", __FILE__) }

  load File.expand_path("../config/routes.rb", __FILE__)
  load File.expand_path("../config/routes_reviews.rb", __FILE__)

  DiscourseEvent.on(:post_created) do |post, _opts, _user|
    next unless SiteSetting.opennotes_enabled
    next unless opennotes_monitored_category?(post.topic&.category)

    Jobs.enqueue(:sync_post_to_opennotes, post_id: post.id)
  end

  DiscourseEvent.on(:post_edited) do |post, _topic_changed|
    next unless SiteSetting.opennotes_enabled
    next unless opennotes_monitored_category?(post.topic&.category)

    Jobs.enqueue(:sync_post_to_opennotes, post_id: post.id, edited: true)
  end

  DiscourseEvent.on(:site_setting_changed) do |name, _old_val, _new_val|
    OpenNotes::PlatformRegistrar.on_setting_saved(name)
  end

  DiscourseEvent.on(:flag_created) do |flag|
    next unless SiteSetting.opennotes_enabled
    next unless SiteSetting.opennotes_route_flags_to_community

    post = flag.post
    next unless post
    next unless opennotes_monitored_category?(post.topic&.category)

    Jobs.enqueue(
      :sync_flag_to_opennotes,
      post_id: post.id,
      flag_type: flag.post_action_type_id,
      flagged_by_id: flag.user_id,
    )
  end

  add_to_serializer(:topic_view, :opennotes_status, include_condition: -> { SiteSetting.opennotes_enabled }) do
    first_post = object.posts&.first
    return unless first_post

    reviewable = ReviewableOpennotesItem.where(target: first_post).order(created_at: :desc).first
    OpenNotes::StatusMapper.display_status(reviewable)
  end

  add_to_serializer(:post, :opennotes_status, include_condition: -> { SiteSetting.opennotes_enabled }) do
    reviewable = ReviewableOpennotesItem.where(target: object).order(created_at: :desc).first
    OpenNotes::StatusMapper.display_status(reviewable)
  end

  def opennotes_monitored_category?(category)
    return false unless category

    monitored = SiteSetting.opennotes_monitored_categories.to_s.split(",").map(&:strip)
    return true if monitored.empty?

    full_slug = category.slug_path.join("/")
    monitored.include?(full_slug) || monitored.include?(category.id.to_s)
  end
end
