from huey.contrib.djhuey import periodic_task, crontab
import logging
import requests

logger = logging.getLogger(__name__)


@periodic_task(crontab(hour="*"))  # Run every hour
def discover_feeds_from_relay_nodes():
    """
    Periodic task to discover new feeds from other Org Social Relay nodes.

    This task:
    1. Fetches the list of relay nodes from the public URL
    2. Filters out our own domain to avoid self-discovery
    3. Calls each relay node's /feeds endpoint to get their registered feeds
    4. Stores newly discovered feeds in our local database
    """
    from django.conf import settings
    from .models import Feed

    relay_list_url = (
        "https://cdn.jsdelivr.net/gh/tanrax/org-social/org-social-relay-list.txt"
    )

    try:
        # Fetch the list of relay nodes
        response = requests.get(relay_list_url, timeout=10)
        response.raise_for_status()

        # The file might be empty or contain one URL per line
        relay_nodes = [
            line.strip() for line in response.text.split("\n") if line.strip()
        ]

        # Filter out our own domain to avoid self-discovery
        site_domain = settings.SITE_DOMAIN
        filtered_nodes = []
        for node_url in relay_nodes:
            # Normalize the URL for comparison
            normalized_node = (
                node_url.replace("http://", "").replace("https://", "").strip("/")
            )
            normalized_site = site_domain.strip("/")

            if normalized_node != normalized_site:
                filtered_nodes.append(node_url)
            else:
                logger.info(f"Skipping own domain: {node_url}")

        relay_nodes = filtered_nodes

        if not relay_nodes:
            logger.info("No relay nodes found in the list after filtering own domain")
            return

        logger.info(
            f"Found {len(relay_nodes)} relay nodes to check (excluding own domain)"
        )

        total_discovered = 0

        for node_url in relay_nodes:
            try:
                # Ensure the URL has proper format
                if not node_url.startswith(("http://", "https://")):
                    node_url = f"http://{node_url}"

                # Call the /feeds endpoint on each relay node
                feeds_url = f"{node_url}/feeds"
                feeds_response = requests.get(feeds_url, timeout=15)
                feeds_response.raise_for_status()

                feeds_data = feeds_response.json()

                # Check if response has expected format
                if feeds_data.get("type") == "Success" and "data" in feeds_data:
                    feeds_list = feeds_data["data"]

                    for feed_url in feeds_list:
                        if isinstance(feed_url, str) and feed_url.strip():
                            # Check if we already have this feed
                            feed_obj, created = Feed.objects.get_or_create(
                                url=feed_url.strip()
                            )

                            if created:
                                total_discovered += 1
                                logger.info(f"Discovered new feed: {feed_url}")

                logger.info(f"Successfully checked relay node: {node_url}")

            except requests.RequestException as e:
                logger.warning(f"Failed to fetch feeds from relay node {node_url}: {e}")
            except ValueError as e:
                logger.warning(f"Invalid JSON response from relay node {node_url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error checking relay node {node_url}: {e}")

        logger.info(
            f"Feed discovery completed. Total new feeds discovered: {total_discovered}"
        )

    except requests.RequestException as e:
        logger.error(f"Failed to fetch relay nodes list from {relay_list_url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in discover_feeds_from_relay_nodes: {e}")
