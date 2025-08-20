'''
Enables the searching and collecting of relevant wiki pages.
'''
from asthralios import config
from atlassian import Confluence
import logging
from typing import Generator, Dict, Optional, List
import json

# Set up logging
logger = logging.getLogger(__name__)

class AtlassianWiki:
    """
    Comprehensive Atlassian Confluence integration class for wiki page management and content retrieval.
    Handles authentication, page listing, page retrieval, and content extraction.
    """

    def __init__(self):
        """
        Initialize AtlassianWiki with Confluence authentication.
        """
        try:
            cfg = config.getInstance().atlassian

            # Validate required configuration
            if not cfg.url:
                raise ValueError("Atlassian URL not configured")
            if not cfg.token:
                raise ValueError("Atlassian token not configured")
            if not hasattr(cfg, 'cloud'):
                raise ValueError("Atlassian cloud flag not configured")

            # Initialize Confluence client
            self.wiki = Confluence(
                url=cfg.url,
                cloud=cfg.cloud,
                token=cfg.token,
            )

            # Test authentication by getting user info
            try:
                user_info = self.wiki.get_user_info()
                logger.info(f"Successfully authenticated to Atlassian Confluence as: {user_info.get('displayName', 'Unknown')}")
            except Exception as e:
                logger.error(f"Failed to authenticate to Atlassian Confluence: {e}")
                raise

        except Exception as e:
            logger.error(f"Failed to initialize Atlassian Confluence client: {e}")
            raise

    def list_pages(self, space_key: Optional[str] = None,
                   page_type: str = "page",
                   status: str = "current",
                   limit: int = 100) -> Generator[Dict, None, None]:
        """
        List pages from Confluence. Returns a generator that yields page information.
        Iterates through all available pages until exhausted.

        Args:
            space_key (str, optional): Filter by space key
            page_type (str): Type of pages to retrieve ('page', 'blogpost', 'attachment')
            status (str): Page status filter ('current', 'archived', 'draft')
            limit (int): Number of pages to retrieve per API call

        Yields:
            Dict: Page information dictionary
        """
        try:
            start = 0
            total_pages = 0

            while True:
                # Get pages with pagination
                if space_key:
                    pages = self.wiki.get_all_pages_from_space(
                        space=space_key,
                        start=start,
                        limit=limit,
                        status=status,
                        type=page_type
                    )
                else:
                    # Get all pages across all spaces
                    pages = self.wiki.get_all_pages(
                        start=start,
                        limit=limit,
                        status=status,
                        type=page_type
                    )

                if not pages:
                    break

                # Process each page
                for page in pages:
                    page_info = {
                        'id': page.get('id'),
                        'title': page.get('title'),
                        'type': page.get('type'),
                        'status': page.get('status'),
                        'space_key': page.get('space', {}).get('key'),
                        'space_name': page.get('space', {}).get('name'),
                        'version': page.get('version', {}).get('number'),
                        'created_date': page.get('createdDate'),
                        'last_modified': page.get('lastModified'),
                        'author': page.get('author', {}).get('displayName'),
                        'url': f"{self.wiki.url}/wiki{page.get('_links', {}).get('webui', '')}",
                        'content_url': page.get('_links', {}).get('content', ''),
                        'expandable': page.get('_expandable', {})
                    }

                    total_pages += 1
                    yield page_info

                # Check if we've reached the end
                if len(pages) < limit:
                    break

                start += limit

            logger.info(f"Retrieved {total_pages} pages from Confluence")

        except Exception as e:
            logger.error(f"Failed to list pages: {e}")
            raise

    def get_page_by_title(self, title: str, space_key: Optional[str] = None) -> Optional[Dict]:
        """
        Get a specific page by its title.

        Args:
            title (str): Title of the page to retrieve
            space_key (str, optional): Space key to search in (faster if specified)

        Returns:
            Optional[Dict]: Page information dictionary or None if not found
        """
        try:
            if space_key:
                # Search in specific space (more efficient)
                pages = self.wiki.get_all_pages_from_space(
                    space=space_key,
                    start=0,
                    limit=1000,  # Large limit to ensure we find the page
                    status="current"
                )
            else:
                # Search across all spaces
                pages = self.wiki.get_all_pages(
                    start=0,
                    limit=1000,
                    status="current"
                )

            # Find page with exact title match
            for page in pages:
                if page.get('title') == title:
                    page_info = {
                        'id': page.get('id'),
                        'title': page.get('title'),
                        'type': page.get('type'),
                        'status': page.get('status'),
                        'space_key': page.get('space', {}).get('key'),
                        'space_name': page.get('space', {}).get('name'),
                        'version': page.get('version', {}).get('number'),
                        'created_date': page.get('createdDate'),
                        'last_modified': page.get('lastModified'),
                        'author': page.get('author', {}).get('displayName'),
                        'url': f"{self.wiki.url}/wiki{page.get('_links', {}).get('webui', '')}",
                        'content_url': page.get('_links', {}).get('content', ''),
                        'expandable': page.get('_expandable', {})
                    }

                    logger.info(f"Found page '{title}' with ID: {page_info['id']}")
                    return page_info

            logger.warning(f"Page with title '{title}' not found")
            return None

        except Exception as e:
            logger.error(f"Failed to get page by title '{title}': {e}")
            raise

    def get_page_content(self, page_id: str, expand: Optional[List[str]] = None) -> Dict:
        """
        Get the full content of a specific page by ID.

        Args:
            page_id (str): ID of the page to retrieve
            expand (List[str], optional): List of fields to expand (e.g., ['body.storage', 'version'])

        Returns:
            Dict: Complete page content with expanded fields
        """
        try:
            # Default expansions for comprehensive content
            if expand is None:
                expand = ['body.storage', 'version', 'space', 'ancestors', 'children.page']

            # Get page with expanded content
            page = self.wiki.get_page_by_id(
                page_id=page_id,
                expand=','.join(expand)
            )

            if not page:
                raise ValueError(f"Page with ID {page_id} not found")

            # Extract and structure the content
            content_info = {
                'id': page.get('id'),
                'title': page.get('title'),
                'type': page.get('type'),
                'status': page.get('status'),
                'space_key': page.get('space', {}).get('key'),
                'space_name': page.get('space', {}).get('name'),
                'version': page.get('version', {}).get('number'),
                'created_date': page.get('createdDate'),
                'last_modified': page.get('lastModified'),
                'author': page.get('author', {}).get('displayName'),
                'url': f"{self.wiki.url}/wiki{page.get('_links', {}).get('webui', '')}",
                'content': {
                    'body': page.get('body', {}).get('storage', {}).get('value', ''),
                    'body_format': page.get('body', {}).get('storage', {}).get('representation', ''),
                },
                'metadata': {
                    'ancestors': page.get('ancestors', []),
                    'children': page.get('children', {}),
                    'descendants': page.get('descendants', {}),
                    'extensions': page.get('extensions', {}),
                }
            }

            logger.info(f"Retrieved content for page '{content_info['title']}' (ID: {page_id})")
            return content_info

        except Exception as e:
            logger.error(f"Failed to get page content for ID {page_id}: {e}")
            raise

    def search_pages(self, query: str, space_key: Optional[str] = None,
                    limit: int = 50, start: int = 0) -> List[Dict]:
        """
        Search for pages using Confluence's search functionality.

        Args:
            query (str): Search query string
            space_key (str, optional): Filter by space key
            limit (int): Maximum number of results to return
            start (int): Starting position for pagination

        Returns:
            List[Dict]: List of matching pages
        """
        try:
            # Build search query
            search_query = f'text ~ "{query}"'
            if space_key:
                search_query += f' AND space = "{space_key}"'

            # Perform search
            search_results = self.wiki.cql(
                query=search_query,
                limit=limit,
                start=start
            )

            # Process search results
            pages = []
            for result in search_results.get('results', []):
                content = result.get('content', {})
                page_info = {
                    'id': content.get('id'),
                    'title': content.get('title'),
                    'type': content.get('type'),
                    'status': content.get('status'),
                    'space_key': content.get('space', {}).get('key'),
                    'space_name': content.get('space', {}).get('name'),
                    'version': content.get('version', {}).get('number'),
                    'created_date': content.get('createdDate'),
                    'last_modified': content.get('lastModified'),
                    'author': content.get('author', {}).get('displayName'),
                    'url': f"{self.wiki.url}/wiki{content.get('_links', {}).get('webui', '')}",
                    'score': result.get('score', 0),
                    'excerpt': result.get('excerpt', '')
                }
                pages.append(page_info)

            logger.info(f"Search for '{query}' returned {len(pages)} results")
            return pages

        except Exception as e:
            logger.error(f"Failed to search for pages with query '{query}': {e}")
            raise

    def get_space_info(self, space_key: str) -> Optional[Dict]:
        """
        Get information about a specific space.

        Args:
            space_key (str): Key of the space to retrieve

        Returns:
            Optional[Dict]: Space information dictionary or None if not found
        """
        try:
            space = self.wiki.get_space(space_key)

            space_info = {
                'key': space.get('key'),
                'name': space.get('name'),
                'type': space.get('type'),
                'status': space.get('status'),
                'description': space.get('description', {}).get('plain', {}).get('value', ''),
                'homepage_id': space.get('homepageId'),
                'created_date': space.get('createdDate'),
                'last_modified': space.get('lastModified'),
                'creator': space.get('creator', {}).get('displayName'),
                'url': f"{self.wiki.url}/wiki/spaces/{space_key}"
            }

            logger.info(f"Retrieved space information for '{space_key}'")
            return space_info

        except Exception as e:
            logger.error(f"Failed to get space info for '{space_key}': {e}")
            return None

    def list_spaces(self, space_type: str = "global") -> List[Dict]:
        """
        List all available spaces.

        Args:
            space_type (str): Type of spaces to retrieve ('global', 'personal', 'archived')

        Returns:
            List[Dict]: List of space information dictionaries
        """
        try:
            spaces = self.wiki.get_all_spaces(space_type=space_type)

            space_list = []
            for space in spaces:
                space_info = {
                    'key': space.get('key'),
                    'name': space.get('name'),
                    'type': space.get('type'),
                    'status': space.get('status'),
                    'description': space.get('description', {}).get('plain', {}).get('value', ''),
                    'homepage_id': space.get('homepageId'),
                    'created_date': space.get('createdDate'),
                    'last_modified': space.get('lastModified'),
                    'creator': space.get('creator', {}).get('displayName'),
                    'url': f"{self.wiki.url}/wiki/spaces/{space.get('key')}"
                }
                space_list.append(space_info)

            logger.info(f"Retrieved {len(space_list)} spaces")
            return space_list

        except Exception as e:
            logger.error(f"Failed to list spaces: {e}")
            raise

    def __del__(self):
        """Cleanup method to ensure proper resource cleanup."""
        try:
            if hasattr(self, 'wiki'):
                # Close any open connections if needed
                pass
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
