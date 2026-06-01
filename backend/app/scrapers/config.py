"""Configuration constants for the Apify Facebook scraper."""

# Number of posts to pull from each group per scrape run
POSTS_PER_RUN = 100

# Sort order for posts within a group
# Apify actor accepts: "newest" or "top"
SORT_ORDER = "CHRONOLOGICAL"

# Apify actor ID for the Facebook Groups scraper
APIFY_ACTOR_ID = "apify/facebook-groups-scraper"

# Apify API base URL
APIFY_API_BASE = "https://api.apify.com/v2"
