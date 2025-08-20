#!/usr/bin/env python3
"""
Pytest test cases for the AtlassianWiki class - Atlassian Confluence integration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from asthralios.adapters.atwiki import AtlassianWiki


class TestAtlassianWiki:
    """Test cases for the AtlassianWiki class."""

    def _create_mock_page(self, page_id, title, space_key="TEST", space_name="Test Space"):
        """Helper method to create a properly mocked page object."""
        mock_page = Mock()
        mock_page.id = page_id
        mock_page.title = title
        mock_page.type = "page"
        mock_page.status = "current"

        # Mock space object with get method
        mock_space = Mock()
        mock_space.key = space_key
        mock_space.name = space_name
        mock_space.get = lambda key, default=None: getattr(mock_space, key, default)
        mock_page.space = mock_space

        # Mock version object with get method
        mock_version = Mock()
        mock_version.number = 1
        mock_version.get = lambda key, default=None: getattr(mock_version, key, default)
        mock_page.version = mock_version

        # Mock timestamps
        mock_page.createdDate = "2024-01-01T00:00:00"
        mock_page.lastModified = "2024-01-01T00:00:00"

        # Mock author object with get method
        mock_author = Mock()
        mock_author.displayName = "Test Author"
        mock_author.get = lambda key, default=None: getattr(mock_author, key, default)
        mock_page.author = mock_author

        # Mock links with get method
        mock_links = Mock()
        mock_links.webui = f"/spaces/{space_key}/pages/{page_id}"
        mock_links.content = f"/rest/api/content/{page_id}"
        mock_links.get = lambda key, default=None: getattr(mock_links, key, default)
        mock_page._links = mock_links

        # Mock expandable
        mock_expandable = {}
        mock_page._expandable = mock_expandable

        # Mock the get method for dictionary-like access
        def mock_get(key, default=None):
            if key == 'id':
                return page_id
            elif key == 'title':
                return title
            elif key == 'type':
                return "page"
            elif key == 'status':
                return "current"
            elif key == 'space':
                return mock_space
            elif key == 'version':
                return mock_version
            elif key == 'createdDate':
                return "2024-01-01T00:00:00"
            elif key == 'lastModified':
                return "2024-01-01T00:00:00"
            elif key == 'author':
                return mock_author
            elif key == '_links':
                return mock_links
            elif key == '_expandable':
                return mock_expandable
            elif key == 'body':
                # Return the body attribute if it exists, otherwise default
                return getattr(mock_page, 'body', default)
            elif key == 'ancestors':
                return getattr(mock_page, 'ancestors', default)
            elif key == 'children':
                return getattr(mock_page, 'children', default)
            elif key == 'descendants':
                return getattr(mock_page, 'descendants', default)
            elif key == 'extensions':
                return getattr(mock_page, 'extensions', default)
            return default

        mock_page.get = mock_get
        return mock_page

    def _create_mock_space(self, space_key, space_name, space_type="global"):
        """Helper method to create a properly mocked space object."""
        mock_space = Mock()
        mock_space.key = space_key
        mock_space.name = space_name
        mock_space.type = space_type
        mock_space.status = "current"

        # Mock description with get method
        mock_description = Mock()
        mock_plain = Mock()
        mock_plain.value = f"This is {space_name}"
        mock_plain.get = lambda key, default=None: getattr(mock_plain, key, default)
        mock_description.plain = mock_plain
        mock_description.get = lambda key, default=None: getattr(mock_description, key, default)
        mock_space.description = mock_description

        # Mock other fields
        mock_space.homepageId = "456"
        mock_space.createdDate = "2024-01-01T00:00:00"
        mock_space.lastModified = "2024-01-01T00:00:00"

        # Mock creator with get method
        mock_creator = Mock()
        mock_creator.displayName = "Test Creator"
        mock_creator.get = lambda key, default=None: getattr(mock_creator, key, default)
        mock_space.creator = mock_creator

        # Mock the get method for dictionary-like access
        def mock_get(key, default=None):
            if key == 'key':
                return space_key
            elif key == 'name':
                return space_name
            elif key == 'type':
                return space_type
            elif key == 'status':
                return "current"
            elif key == 'description':
                return mock_description
            elif key == 'homepageId':
                return "456"
            elif key == 'createdDate':
                return "2024-01-01T00:00:00"
            elif key == 'lastModified':
                return "2024-01-01T00:00:00"
            elif key == 'creator':
                return mock_creator
            return default

        mock_space.get = mock_get
        return mock_space

    @pytest.fixture
    def mock_config(self):
        """Mock configuration with Atlassian settings."""
        mock_cfg = Mock()
        mock_cfg.atlassian.url = "https://test.atlassian.net"
        mock_cfg.atlassian.cloud = True
        mock_cfg.atlassian.token = "test_token_12345"
        return mock_cfg

    @pytest.fixture
    def mock_confluence_client(self):
        """Mock Confluence client."""
        mock_client = Mock()
        mock_client.url = "https://test.atlassian.net"
        return mock_client

    @pytest.fixture
    def atwiki_instance(self, mock_config, mock_confluence_client):
        """Create an AtlassianWiki instance with mocked dependencies."""
        with patch('asthralios.adapters.atwiki.config') as mock_config_module:
            mock_config_module.getInstance.return_value = mock_config

            with patch('asthralios.adapters.atwiki.Confluence') as mock_confluence_class:
                mock_confluence_class.return_value = mock_confluence_client

                # Mock successful authentication - use a method that actually exists
                mock_confluence_client.get_all_spaces.return_value = []

                atwiki = AtlassianWiki()
                return atwiki

    def test_initialization_success(self, mock_config):
        """Test successful AtlassianWiki initialization."""
        with patch('asthralios.adapters.atwiki.config') as mock_config_module:
            mock_config_module.getInstance.return_value = mock_config

            with patch('asthralios.adapters.atwiki.Confluence') as mock_confluence_class:
                mock_client = Mock()
                mock_client.url = "https://test.atlassian.net"
                # Use a method that actually exists in Confluence API
                mock_client.get_all_spaces.return_value = []
                mock_confluence_class.return_value = mock_client

                atwiki = AtlassianWiki()
                assert atwiki.wiki is not None
                assert atwiki.wiki.url == "https://test.atlassian.net"

    def test_initialization_missing_url(self):
        """Test initialization fails when URL is missing."""
        with patch('asthralios.adapters.atwiki.config') as mock_config_module:
            mock_cfg = Mock()
            mock_cfg.atlassian.url = None
            mock_cfg.atlassian.cloud = True
            mock_cfg.atlassian.token = "test_token"
            mock_config_module.getInstance.return_value = mock_cfg

            with pytest.raises(ValueError, match="Atlassian URL not configured"):
                AtlassianWiki()

    def test_initialization_missing_token(self):
        """Test initialization fails when token is missing."""
        with patch('asthralios.adapters.atwiki.config') as mock_config_module:
            mock_cfg = Mock()
            mock_cfg.atlassian.url = "https://test.atlassian.net"
            mock_cfg.atlassian.cloud = True
            mock_cfg.atlassian.token = None
            mock_config_module.getInstance.return_value = mock_cfg

            with pytest.raises(ValueError, match="Atlassian token not configured"):
                AtlassianWiki()

    def test_initialization_missing_cloud_flag(self):
        """Test initialization fails when cloud flag is missing."""
        with patch('asthralios.adapters.atwiki.config') as mock_config_module:
            mock_cfg = Mock()
            mock_cfg.atlassian.url = "https://test.atlassian.net"
            # No cloud attribute
            mock_cfg.atlassian.token = "test_token"
            # Ensure cloud attribute is not present
            delattr(mock_cfg.atlassian, 'cloud')
            mock_config_module.getInstance.return_value = mock_cfg

            with patch('asthralios.adapters.atwiki.Confluence') as mock_confluence_class:
                mock_client = Mock()
                mock_client.url = "https://test.atlassian.net"
                mock_confluence_class.return_value = mock_client

                with pytest.raises(ValueError, match="Atlassian cloud flag not configured"):
                    AtlassianWiki()

    def test_initialization_authentication_failure(self, mock_config):
        """Test initialization fails when authentication fails."""
        with patch('asthralios.adapters.atwiki.config') as mock_config_module:
            mock_config_module.getInstance.return_value = mock_config

            with patch('asthralios.adapters.atwiki.Confluence') as mock_confluence_class:
                mock_client = Mock()
                mock_client.url = "https://test.atlassian.net"
                # Use a method that actually exists but make it fail
                mock_client.get_all_spaces.side_effect = Exception("Auth failed")
                mock_confluence_class.return_value = mock_client

                with pytest.raises(Exception, match="Auth failed"):
                    AtlassianWiki()

    def test_list_pages_success(self, atwiki_instance):
        """Test successful page listing."""
        # Use helper method to create properly mocked page
        mock_page = self._create_mock_page("123", "Test Page")

        atwiki_instance.wiki.get_all_pages.return_value = [mock_page]

        pages = list(atwiki_instance.list_pages())

        assert len(pages) == 1
        page = pages[0]
        assert page['id'] == "123"
        assert page['title'] == "Test Page"
        assert page['type'] == "page"
        assert page['space_key'] == "TEST"
        assert page['space_name'] == "Test Space"

    def test_list_pages_with_space_filter(self, atwiki_instance):
        """Test page listing with space filter."""
        atwiki_instance.wiki.get_all_pages_from_space.return_value = []

        list(atwiki_instance.list_pages(space_key="TEST"))

        atwiki_instance.wiki.get_all_pages_from_space.assert_called_with(
            space="TEST", start=0, limit=100, status="current", type="page"
        )

    def test_list_pages_with_custom_filters(self, atwiki_instance):
        """Test page listing with custom filters."""
        atwiki_instance.wiki.get_all_pages.return_value = []

        list(atwiki_instance.list_pages(page_type="blogpost", status="archived", limit=50))

        atwiki_instance.wiki.get_all_pages.assert_called_with(
            start=0, limit=50, status="archived", type="blogpost"
        )

    def test_list_pages_pagination(self, atwiki_instance):
        """Test page listing with pagination."""
        # Use helper methods to create properly mocked pages
        mock_page1 = self._create_mock_page("1", "Page 1")
        mock_page2 = self._create_mock_page("2", "Page 2")

        # Mock pagination behavior
        # First call returns 2 pages (equal to limit), second call returns empty (no more pages)
        atwiki_instance.wiki.get_all_pages.side_effect = [
            [mock_page1, mock_page2],  # First call returns 2 pages
            []                          # Second call returns empty list (no more pages)
        ]

        pages = list(atwiki_instance.list_pages(limit=2))

        assert len(pages) == 2
        assert pages[0]['title'] == "Page 1"
        assert pages[1]['title'] == "Page 2"
        assert atwiki_instance.wiki.get_all_pages.call_count == 2

    def test_get_page_by_title_success(self, atwiki_instance):
        """Test successful page retrieval by title."""
        # Use helper method to create properly mocked page
        mock_page = self._create_mock_page("123", "Test Page")

        atwiki_instance.wiki.get_all_pages.return_value = [mock_page]

        page = atwiki_instance.get_page_by_title("Test Page")

        assert page is not None
        assert page['id'] == "123"
        assert page['title'] == "Test Page"
        assert page['space_key'] == "TEST"

    def test_get_page_by_title_not_found(self, atwiki_instance):
        """Test page retrieval by title when page doesn't exist."""
        atwiki_instance.wiki.get_all_pages.return_value = []

        page = atwiki_instance.get_page_by_title("Nonexistent Page")

        assert page is None

    def test_get_page_by_title_with_space_filter(self, atwiki_instance):
        """Test page retrieval by title with space filter."""
        atwiki_instance.wiki.get_all_pages_from_space.return_value = []

        page = atwiki_instance.get_page_by_title("Test Page", space_key="TEST")

        assert page is None
        atwiki_instance.wiki.get_all_pages_from_space.assert_called_with(
            space="TEST", start=0, limit=1000, status="current"
        )

    def test_get_page_content_success(self, atwiki_instance):
        """Test successful page content retrieval."""
        # Use helper method to create properly mocked page
        mock_page = self._create_mock_page("123", "Test Page")

        # Mock body content with proper nested structure
        mock_body = Mock()
        mock_storage = Mock()
        mock_storage.value = "<p>This is test content</p>"
        mock_storage.representation = "storage"

        # Set up the mock to return the storage object when get('storage') is called
        mock_body.get = lambda key, default=None: mock_storage if key == 'storage' else default

        # Set up the storage mock to return values when get() is called
        mock_storage.get = lambda key, default=None: getattr(mock_storage, key, default)

        mock_page.body = mock_body

        # Mock metadata
        mock_page.ancestors = []
        mock_page.children = {}
        mock_page.descendants = {}
        mock_page.extensions = {}

        atwiki_instance.wiki.get_page_by_id.return_value = mock_page

        content = atwiki_instance.get_page_content("123")

        assert content['id'] == "123"
        assert content['title'] == "Test Page"
        assert content['content']['body'] == "<p>This is test content</p>"
        assert content['content']['body_format'] == "storage"
        assert content['space_key'] == "TEST"

    def test_get_page_content_not_found(self, atwiki_instance):
        """Test page content retrieval when page doesn't exist."""
        atwiki_instance.wiki.get_page_by_id.return_value = None

        with pytest.raises(ValueError, match="Page with ID 123 not found"):
            atwiki_instance.get_page_content("123")

    def test_get_page_content_with_custom_expand(self, atwiki_instance):
        """Test page content retrieval with custom expand fields."""
        # Use helper method to create properly mocked page
        mock_page = self._create_mock_page("123", "Test Page")

        # Mock body content
        mock_body = Mock()
        mock_storage = Mock()
        mock_storage.value = "Content"
        mock_storage.representation = "storage"
        mock_page.body = mock_body
        mock_page.body.storage = mock_storage

        # Mock metadata
        mock_page.ancestors = []
        mock_page.children = {}
        mock_page.descendants = {}
        mock_page.extensions = {}

        atwiki_instance.wiki.get_page_by_id.return_value = mock_page

        custom_expand = ['body.storage', 'version']
        atwiki_instance.get_page_content("123", expand=custom_expand)

        atwiki_instance.wiki.get_page_by_id.assert_called_with(
            page_id="123", expand="body.storage,version"
        )

    def test_search_pages_success(self, atwiki_instance):
        """Test successful page search."""
        # Use helper method to create properly mocked page
        mock_content = self._create_mock_page("123", "Test Page")

        # Mock search result with proper get method
        mock_result = Mock()
        mock_result.content = mock_content
        mock_result.score = 0.95
        mock_result.excerpt = "This is a test page about documentation"

        # Set up the mock to return the content when get('content') is called
        mock_result.get = lambda key, default=None: mock_content if key == 'content' else getattr(mock_result, key, default)

        atwiki_instance.wiki.cql.return_value = {'results': [mock_result]}

        results = atwiki_instance.search_pages("documentation")

        assert len(results) == 1
        result = results[0]
        assert result['id'] == "123"
        assert result['title'] == "Test Page"
        assert result['score'] == 0.95
        assert result['excerpt'] == "This is a test page about documentation"

    def test_search_pages_with_space_filter(self, atwiki_instance):
        """Test page search with space filter."""
        atwiki_instance.wiki.cql.return_value = {'results': []}

        atwiki_instance.search_pages("documentation", space_key="TEST")

        expected_query = 'text ~ "documentation" AND space = "TEST"'
        atwiki_instance.wiki.cql.assert_called_with(
            query=expected_query, limit=50, start=0
        )

    def test_search_pages_with_custom_parameters(self, atwiki_instance):
        """Test page search with custom parameters."""
        atwiki_instance.wiki.cql.return_value = {'results': []}

        atwiki_instance.search_pages("documentation", limit=100, start=50)

        atwiki_instance.wiki.cql.assert_called_with(
            query='text ~ "documentation"', limit=100, start=50
        )

    def test_get_space_info_success(self, atwiki_instance):
        """Test successful space information retrieval."""
        # Use helper method to create properly mocked space
        mock_space = self._create_mock_space("TEST", "Test Space")

        atwiki_instance.wiki.get_space.return_value = mock_space

        space_info = atwiki_instance.get_space_info("TEST")

        assert space_info['key'] == "TEST"
        assert space_info['name'] == "Test Space"
        assert space_info['type'] == "global"
        assert space_info['status'] == "current"
        assert space_info['description'] == "This is Test Space"
        assert space_info['creator'] == "Test Creator"

    def test_get_space_info_not_found(self, atwiki_instance):
        """Test space info retrieval when space doesn't exist."""
        atwiki_instance.wiki.get_space.side_effect = Exception("Space not found")

        space_info = atwiki_instance.get_space_info("NONEXISTENT")

        assert space_info is None

    def test_list_spaces_success(self, atwiki_instance):
        """Test successful space listing."""
        # Use helper method to create properly mocked space
        mock_space = self._create_mock_space("TEST", "Test Space")

        atwiki_instance.wiki.get_all_spaces.return_value = [mock_space]

        spaces = atwiki_instance.list_spaces()

        assert len(spaces) == 1
        space = spaces[0]
        assert space['key'] == "TEST"
        assert space['name'] == "Test Space"
        assert space['type'] == "global"

    def test_list_spaces_with_type_filter(self, atwiki_instance):
        """Test space listing with type filter."""
        atwiki_instance.wiki.get_all_spaces.return_value = []

        atwiki_instance.list_spaces(space_type="personal")

        atwiki_instance.wiki.get_all_spaces.assert_called_with(space_type="personal")

    def test_cleanup_method(self, atwiki_instance):
        """Test cleanup method execution."""
        # This test ensures the cleanup method doesn't raise exceptions
        atwiki_instance.__del__()

        # The method should execute without errors
        assert True


if __name__ == "__main__":
    pytest.main([__file__])
