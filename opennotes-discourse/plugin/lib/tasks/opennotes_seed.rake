# frozen_string_literal: true

desc "Seed Discourse with OpenNotes demo content from corpus"
task "opennotes:seed" => :environment do
  corpus_path = File.join(
    Rails.root,
    "plugins/discourse-opennotes/data/seed-corpus/corpus.json",
  )

  unless File.exist?(corpus_path)
    puts "ERROR: Corpus not found at #{corpus_path}"
    exit 1
  end

  corpus = JSON.parse(File.read(corpus_path))
  RateLimiter.disable

  opennotes_was_enabled = SiteSetting.opennotes_enabled
  SiteSetting.opennotes_enabled = false

  admin = User.find_by(username: "admin") || Discourse.system_user

  puts "==> Creating users..."
  corpus["users"].each do |u|
    existing = User.find_by(username: u["username"])
    if existing
      puts "  [skip] #{u["username"]} already exists"
      next
    end

    user = User.create!(
      username: u["username"],
      email: u["email"],
      password: SecureRandom.hex(16),
      active: true,
      approved: true,
    )
    user.activate
    user.change_trust_level!(u["trust_level"])
    puts "  [create] #{u["username"]} (TL#{u["trust_level"]})"
  end

  puts "\n==> Creating categories..."
  monitored_slugs = []

  corpus["categories"].each do |cat|
    parent = Category.find_by(slug: cat["slug"], parent_category_id: nil)
    unless parent
      parent = Category.create!(
        name: cat["name"],
        slug: cat["slug"],
        color: cat["color"],
        text_color: cat["text_color"] || "FFFFFF",
        user: admin,
      )
      puts "  [create] #{cat["name"]}"
    else
      puts "  [skip] #{cat["name"]} already exists"
    end

    (cat["subcategories"] || []).each do |sub|
      child = Category.find_by(slug: sub["slug"], parent_category_id: parent.id)
      unless child
        child = Category.create!(
          name: sub["name"],
          slug: sub["slug"],
          color: sub["color"],
          text_color: sub["text_color"] || "FFFFFF",
          parent_category_id: parent.id,
          user: admin,
        )
        puts "  [create] #{cat["slug"]}/#{sub["slug"]}"
      else
        puts "  [skip] #{cat["slug"]}/#{sub["slug"]} already exists"
      end
      monitored_slugs << "#{cat["slug"]}/#{sub["slug"]}"
    end
  end

  puts "\n==> Creating topics and posts..."
  corpus["topics"].each do |topic_data|
    category = resolve_category(topic_data["category"])
    unless category
      puts "  [warn] Category not found: #{topic_data["category"]}, skipping topic"
      next
    end

    author = User.find_by(username: topic_data["author"])
    unless author
      puts "  [warn] Author not found: #{topic_data["author"]}, skipping topic"
      next
    end

    existing_topic = Topic.where(title: topic_data["title"], category_id: category.id).first
    if existing_topic
      puts "  [skip] Topic: #{topic_data["title"]}"
      next
    end

    first_post_body = topic_data["posts"][0]["body"]
    creator = PostCreator.new(
      author,
      title: topic_data["title"],
      raw: first_post_body,
      category: category.id,
      skip_validations: true,
    )
    result = creator.create
    unless result&.persisted?
      puts "  [error] Failed to create topic: #{topic_data["title"]} — #{creator.errors.full_messages.join(", ")}"
      next
    end

    puts "  [create] Topic: #{topic_data["title"]}"
    topic = result.topic

    topic_data["posts"][1..].each_with_index do |post_data, idx|
      reply_author = User.find_by(username: post_data["author"])
      unless reply_author
        puts "    [warn] Reply author not found: #{post_data["author"]}, skipping"
        next
      end

      reply_creator = PostCreator.new(
        reply_author,
        topic_id: topic.id,
        raw: post_data["body"],
        reply_to_post_number: post_data["reply_to_post_number"],
        skip_validations: true,
      )
      reply = reply_creator.create
      if reply&.persisted?
        puts "    [create] Reply #{idx + 2} by #{post_data["author"]}"
      else
        puts "    [error] Reply by #{post_data["author"]} — #{reply_creator.errors.full_messages.join(", ")}"
      end
    end

    create_flags(topic, topic_data["flags"]) if topic_data["flags"]&.any?
  end

  puts "\n==> Configuring monitored categories..."
  if monitored_slugs.any?
    SiteSetting.opennotes_monitored_categories = monitored_slugs.join(",")
    puts "  Set opennotes_monitored_categories = #{monitored_slugs.join(",")}"
  end

  SiteSetting.opennotes_enabled = opennotes_was_enabled
  RateLimiter.enable

  puts "\n==> Seed complete!"
  puts "  Users: #{User.real.count} total"
  puts "  Categories: #{Category.count} total"
  puts "  Topics: #{Topic.count} total"
  puts "  Posts: #{Post.count} total"
end

def resolve_category(path)
  parts = path.split("/")
  if parts.length == 1
    Category.find_by(slug: parts[0], parent_category_id: nil)
  else
    parent = Category.find_by(slug: parts[0], parent_category_id: nil)
    return nil unless parent
    Category.find_by(slug: parts[1], parent_category_id: parent.id)
  end
end

def create_flags(topic, flags)
  posts = topic.posts.order(:post_number).to_a

  flags.each do |flag_data|
    post = posts[flag_data["post_index"]]
    unless post
      puts "    [warn] Flag target post_index #{flag_data["post_index"]} not found"
      next
    end

    flagger = User.find_by(username: flag_data["flagged_by"])
    unless flagger
      puts "    [warn] Flagger not found: #{flag_data["flagged_by"]}"
      next
    end

    flag_type_sym = flag_data["flag_type"].to_sym
    type_id = PostActionType.types[flag_type_sym]
    unless type_id
      puts "    [warn] Unknown flag type: #{flag_data["flag_type"]}"
      next
    end

    if PostAction.where(user_id: flagger.id, post_id: post.id, post_action_type_id: type_id).exists?
      puts "    [skip] Flag on post #{post.post_number} by #{flag_data["flagged_by"]}"
      next
    end

    result = PostActionCreator.new(
      flagger,
      post,
      type_id,
      message: "Flagged during seed",
    ).perform
    if result.success?
      puts "    [create] Flag on post #{post.post_number} by #{flag_data["flagged_by"]} (#{flag_data["flag_type"]})"
    else
      puts "    [error] Flag failed: #{result.errors&.full_messages&.join(", ")}"
    end
  end
end
