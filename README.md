# Subotica source expansion (additive)

**Do not overwrite your existing `generate_feeds.py`, its GitHub Actions workflow, or the five existing feeds.** Copy `sources.json`, `build.py`, `requirements.txt`, and `.github/workflows/update-subotica-feeds.yml` into the root of your existing GitHub Pages repository.

1. GitHub Actions → **Update Subotica source feeds** → Run workflow.
2. Open `status.json`. Only `existing_feed`, `native_feed_found` and `generated` indicate a feed exists. `needs_custom_parser`, `fetch_failed`, `needs_url` are **not connected**.
3. For `native_feed_found`, use the `url` value directly in n8n. For `generated`, use `https://anatolyspirin730.github.io/-serbia-local-rss/feeds/<id>.xml`.
4. **Do not import all sources into n8n until verified**: the generated feeds may be empty or may include irrelevant articles. For broader regional sources, use editorial geographic filtering.
5. This is a *discovery + safe first-pass generator*, not a guarantee that all 29 sources are connected. Websites without machine-readable publication dates require custom parsers; the script deliberately does not assign the crawl date as the publication date.

Caution: Some sites may prohibit automated scraping or block GitHub runners; respect site policies. A native feed might be general rather than Subotica-specific.
