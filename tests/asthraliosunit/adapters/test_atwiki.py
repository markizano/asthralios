#!/usr/bin/env python3
"""
Example usage of the AtlassianWiki class for Confluence integration and page management.
This demonstrates all the main functionality of the AtlassianWiki class.
"""

from asthralios.adapters.atwiki import AtlassianWiki
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

def main():
    """Example usage of the AtlassianWiki class."""
    
    try:
        # Initialize AtlassianWiki
        wiki = AtlassianWiki()
        print("✅ Successfully connected to Atlassian Confluence")
        
        # Example 1: List all available spaces
        print("\n🏢 Getting available spaces...")
        spaces = wiki.list_spaces()
        print(f"Found {len(spaces)} spaces:")
        for space in spaces[:5]:  # Show first 5 spaces
            print(f"  - {space['name']} ({space['key']}) - {space['type']}")
        
        if spaces:
            # Use the first space for examples
            first_space = spaces[0]['key']
            print(f"\n📚 Using space '{first_space}' for page examples...")
            
            # Example 2: List pages in a specific space (using generator)
            print(f"\n📄 Listing pages in space '{first_space}'...")
            page_count = 0
            for page in wiki.list_pages(space_key=first_space, limit=10):
                print(f"  - {page['title']} (ID: {page['id']}) - {page['status']}")
                page_count += 1
                if page_count >= 5:  # Limit to first 5 pages for demo
                    break
            print(f"Retrieved {page_count} pages from space '{first_space}'")
            
            # Example 3: Search for pages
            print(f"\n🔍 Searching for pages containing 'documentation'...")
            search_results = wiki.search_pages("documentation", space_key=first_space, limit=5)
            print(f"Search returned {len(search_results)} results:")
            for result in search_results:
                print(f"  - {result['title']} (Score: {result['score']})")
                if result.get('excerpt'):
                    print(f"    Excerpt: {result['excerpt'][:100]}...")
            
            # Example 4: Get page by title
            if page_count > 0:
                print(f"\n📖 Getting page by title...")
                # Get the first page we found
                first_page = None
                for page in wiki.list_pages(space_key=first_space, limit=1):
                    first_page = page
                    break
                
                if first_page:
                    page_by_title = wiki.get_page_by_title(first_page['title'], space_key=first_space)
                    if page_by_title:
                        print(f"Found page: {page_by_title['title']}")
                        print(f"  ID: {page_by_title['id']}")
                        print(f"  Author: {page_by_title['author']}")
                        print(f"  URL: {page_by_title['url']}")
                        
                        # Example 5: Get full page content
                        print(f"\n📄 Getting full content for page '{page_by_title['title']}'...")
                        try:
                            page_content = wiki.get_page_content(page_by_title['id'])
                            print(f"Content retrieved successfully!")
                            print(f"  Title: {page_content['title']}")
                            print(f"  Body length: {len(page_content['content']['body'])} characters")
                            print(f"  Body format: {page_content['content']['body_format']}")
                            
                            # Show first 200 characters of content
                            body_preview = page_content['content']['body'][:200]
                            if len(page_content['content']['body']) > 200:
                                body_preview += "..."
                            print(f"  Content preview: {body_preview}")
                            
                            # Show metadata
                            if page_content['metadata']['ancestors']:
                                print(f"  Ancestors: {len(page_content['metadata']['ancestors'])} parent pages")
                            
                        except Exception as e:
                            print(f"❌ Failed to get page content: {e}")
                    else:
                        print(f"❌ Page not found by title")
            
            # Example 6: Get space information
            print(f"\n🏢 Getting detailed space information...")
            space_info = wiki.get_space_info(first_space)
            if space_info:
                print(f"Space: {space_info['name']} ({space_info['key']})")
                print(f"  Type: {space_info['type']}")
                print(f"  Status: {space_info['status']}")
                print(f"  Description: {space_info['description'][:100] if space_info['description'] else 'No description'}")
                print(f"  Creator: {space_info['creator']}")
                print(f"  URL: {space_info['url']}")
        
        # Example 7: List all pages across all spaces (generator example)
        print(f"\n🌐 Listing all pages across all spaces (first 10)...")
        all_pages_count = 0
        for page in wiki.list_pages(limit=50):  # Use larger limit for cross-space search
            print(f"  - {page['title']} in {page['space_name']} ({page['space_key']})")
            all_pages_count += 1
            if all_pages_count >= 10:  # Limit to first 10 for demo
                break
        print(f"Retrieved {all_pages_count} pages across all spaces")
        
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("Make sure you have set up your Atlassian configuration in the config file.")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Check your Atlassian URL, token, and cloud configuration.")

def demonstrate_generator_usage():
    """Demonstrate the generator functionality for listing pages."""
    print("\n" + "="*60)
    print("GENERATOR USAGE DEMONSTRATION")
    print("="*60)
    
    try:
        wiki = AtlassianWiki()
        
        # Get all pages using the generator
        print("Using generator to iterate through all pages...")
        total_pages = 0
        space_counts = {}
        
        for page in wiki.list_pages(limit=100):  # Process in batches of 100
            total_pages += 1
            space_key = page['space_key']
            space_counts[space_key] = space_counts.get(space_key, 0) + 1
            
            # Show progress every 50 pages
            if total_pages % 50 == 0:
                print(f"Processed {total_pages} pages so far...")
            
            # Limit for demo purposes
            if total_pages >= 200:
                print("Reached demo limit of 200 pages")
                break
        
        print(f"\n📊 Summary:")
        print(f"Total pages processed: {total_pages}")
        print(f"Spaces found: {len(space_counts)}")
        for space_key, count in sorted(space_counts.items())[:5]:  # Show top 5 spaces
            print(f"  {space_key}: {count} pages")
        
    except Exception as e:
        print(f"❌ Error in generator demo: {e}")

if __name__ == "__main__":
    main()
    demonstrate_generator_usage()
