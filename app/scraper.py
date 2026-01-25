import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

async def scrape_site(page, url, days):
    logger.info(f"Scraping {url}")
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        
        # Simple heuristic to extract article links
        # We look for 'a' tags that might be headlines.
        # This is a generic approach.
        links = await page.evaluate('''() => {
            const anchors = Array.from(document.querySelectorAll('a'));
            return anchors.map(a => ({
                href: a.href,
                text: a.innerText.trim(),
            })).filter(a => a.href && a.text.length > 10);
        }''')
        
        # Filter links:
        # 1. Must be from the same domain (mostly) or subdomains.
        # 2. Unique
        # 3. Text length meaningful
        
        seen = set()
        articles = []
        base_domain = urlparse(url).netloc
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Limit to top 5 candidates per site to avoid explosion in demo
        candidates = []
        for l in links:
            if l['href'] in seen:
                continue
            seen.add(l['href'])
            
            # Skip likely non-article links
            if any(x in l['href'].lower() for x in ['login', 'register', 'contact', 'about', 'privacy', 'terms', 'category', 'tag', 'search']):
                continue
            
            # Check domain
            link_domain = urlparse(l['href']).netloc
            if base_domain not in link_domain and link_domain not in base_domain:
               continue
               
            candidates.append(l)
            if len(candidates) >= 5:
                break
        
        # Now visit candidates to get content
        for candidate in candidates:
            try:
                # In a real app, we would parallelize this carefully
                await page.goto(candidate['href'], timeout=15000)
                await page.wait_for_load_state("domcontentloaded")
                
                # Extract main content
                # Heuristic: largest text block or specific selectors
                content = await page.evaluate('''() => {
                    // Remove nav, footer, ads to clean up
                    const ignore = ['nav', 'footer', 'header', 'script', 'style', 'noscript', 'iframe'];
                    ignore.forEach(tag => {
                        document.querySelectorAll(tag).forEach(e => e.remove());
                    });
                    return document.body.innerText; 
                }''')
                
                if len(content) > 200: # Min length to be useful
                    articles.append({
                        "source": url,
                        "title": candidate['text'],
                        "url": candidate['href'],
                        "content": content[:10000] # Truncate to avoid huge payload
                    })
            except Exception as e:
                logger.error(f"Failed to scrape article {candidate['href']}: {e}")
                continue
                
        return articles

    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return []

async def scrape_urls(urls: list[str], days: int = 7):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        tasks = []
        all_articles = []
        
        # Process sequentially per page to reuse context/page or parallelize?
        # Parallelize pages
        
        # Limit concurrency
        semaphore = asyncio.Semaphore(3)
        
        async def fetch(url):
            async with semaphore:
                page = await context.new_page()
                try:
                    site_articles = await scrape_site(page, url, days)
                    all_articles.extend(site_articles)
                finally:
                    await page.close()

        await asyncio.gather(*[fetch(url) for url in urls])
        await browser.close()
        
        return all_articles
