#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! docker ps -q -f name=discourse_dev | grep -q .; then
  echo "Error: discourse_dev container is not running"
  echo "Run bootstrap.sh first: bash docker/bootstrap.sh"
  exit 1
fi

echo "==> Seeding Discourse with test data..."

# Write Ruby script to temp file to avoid shell quoting issues
SEED_SCRIPT=$(mktemp)
cat > "$SEED_SCRIPT" << 'RUBY'
SiteSetting.min_admin_password_length = 10
SiteSetting.min_password_length = 8
RateLimiter.disable

users = [
  { username: 'reviewer1', email: 'reviewer1@test.local', trust_level: 2 },
  { username: 'reviewer2', email: 'reviewer2@test.local', trust_level: 2 },
  { username: 'newuser',   email: 'newuser@test.local',   trust_level: 0 },
]

users.each do |u|
  if User.find_by(username: u[:username])
    puts "User #{u[:username]} already exists, skipping"
    next
  end

  user = User.create!(
    username: u[:username],
    email: u[:email],
    password: 'password-for-testing',
    active: true,
    approved: true
  )
  user.activate
  user.change_trust_level!(u[:trust_level])
  puts "Created user: #{u[:username]} (TL#{u[:trust_level]})"
end

admin = User.find_by(username: 'admin') || Discourse.system_user
categories = [
  { name: 'General Discussion', slug: 'general-discussion', color: '0088CC' },
  { name: 'Announcements',      slug: 'announcements',      color: 'BF1E2E' },
  { name: 'Off Topic',          slug: 'off-topic',          color: '92278F' },
]

categories.each do |c|
  if Category.find_by(slug: c[:slug])
    puts "Category #{c[:name]} already exists, skipping"
    next
  end

  Category.create!(
    name: c[:name],
    slug: c[:slug],
    color: c[:color],
    text_color: 'FFFFFF',
    user: admin
  )
  puts "Created category: #{c[:name]}"
end

reviewer = User.find_by(username: 'reviewer1')
general = Category.find_by(slug: 'general-discussion')

if general && reviewer
  existing = Topic.where(user: reviewer, category: general).count
  if existing == 0
    PostCreator.create!(
      reviewer,
      title: 'Welcome to General Discussion',
      raw: 'This is a sample post in the General Discussion category.',
      category: general.id
    )
    puts 'Created sample post in General Discussion'

    PostCreator.create!(
      reviewer,
      title: 'Community Guidelines',
      raw: 'Please be respectful and follow community guidelines when posting.',
      category: general.id
    )
    puts 'Created sample post: Community Guidelines'
  else
    puts 'Sample posts already exist, skipping'
  end
end

puts ''
puts '==> Seed complete!'
puts "Users: #{User.real.count} total"
puts "Categories: #{Category.count} total"
puts "Topics: #{Topic.count} total"
RUBY

docker cp "$SEED_SCRIPT" discourse_dev:/src/tmp/seed.rb
rm "$SEED_SCRIPT"

docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rails runner tmp/seed.rb"

echo "==> Seeding done!"
