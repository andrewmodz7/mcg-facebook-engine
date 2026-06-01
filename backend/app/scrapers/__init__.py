"""Apify Facebook Groups scraper package."""

from .apify_client import ApifyError
from .facebook_groups import scrape_all_active_groups, scrape_group

__all__ = ["ApifyError", "scrape_all_active_groups", "scrape_group"]
