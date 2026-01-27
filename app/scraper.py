import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
import logging
from urllib.parse import urlparse
from google import genai
import json
from .config import get_settings

logger = logging.getLogger(__name__)

async def scrape_site(page, url, days, target):
    logger.info(f"Scraping {url} for target: {target}")
    settings = get_settings()
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
            if len(candidates) >= settings.get("max_scrape_size", 20):
                break
        
        # Filter candidates using LLM
        api_key = settings.get("gemini_api_key")
        
        if not api_key:
            raise ValueError("Gemini API Key is missing in settings")
        
        filtered_candidates = []
        try:
                client = genai.Client(api_key=api_key)
                prompt = f"""
                You are a news editor. Select the most relevant articles for a "{target}" audience from the list below.
                Return a JSON object with a key "urls" containing a list of strings of the selected URLs.
                Select at most 5 articles.
                
                Articles:
                {json.dumps([{'url': c['href'], 'text': c['text']} for c in candidates], ensure_ascii=False)}
                """
                
                response = client.models.generate_content(
                    model=settings.get("gemini_model", "gemini-2.5-flash"),
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                
                try:
                    selected_urls = json.loads(response.text).get("urls", [])
                    logger.info(f"LLM filtered {len(candidates)} -> {len(selected_urls)} articles.")
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON from LLM: {response.text}")
                    selected_urls = []

                for c in candidates:
                    if c['href'] in selected_urls:
                        filtered_candidates.append(c)
                
                # If LLM returns fewer than expected or nothing, we might want to fill up, but user asked for target.
                # If 0, fallback to simple top 5? 
                # "targetに指定された情報を参考にして取得するようにしなさい" -> If none match, maybe none should be returned?
                # But to maintain usability, if LLM fails completely (empty), maybe default to top 5.
                if not filtered_candidates and candidates:
                    logger.warning("LLM selected 0 articles. Falling back to top 3.")
                    filtered_candidates = candidates[:3]

        except Exception as e:
            logger.error(f"Error filtering candidates with LLM: {e}")
            
            # Fallback to default model if different
            model_name = settings.get("gemini_model", settings["default_gemini_model"])
            default_model = settings["default_gemini_model"]
            
            if model_name != default_model:
                try:
                    logger.warning(f"Falling back to default model: {default_model}")
                    response = client.models.generate_content(
                        model=default_model,
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                     
                    try:
                        selected_urls = json.loads(response.text).get("urls", [])
                        logger.info(f"LLM (fallback) filtered {len(candidates)} -> {len(selected_urls)} articles.")
                        
                        for c in candidates:
                            if c['href'] in selected_urls:
                                filtered_candidates.append(c)
                                
                        if not filtered_candidates and candidates:
                             filtered_candidates = candidates[:3]
                             
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON from LLM fallback: {response.text}")
                        filtered_candidates = candidates[:5]

                except Exception as e2:
                    logger.error(f"Error filtering with fallback model {default_model}: {e2}")
                    filtered_candidates = candidates[:5]
            else:
                filtered_candidates = candidates[:5]

        # Now visit candidates to get content
        for candidate in filtered_candidates:
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

async def scrape_urls(urls: list[str], days: int = 7, target: str = "Beginner"):
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
                    site_articles = await scrape_site(page, url, days, target)
                    all_articles.extend(site_articles)
                finally:
                    await page.close()

        await asyncio.gather(*[fetch(url) for url in urls])
        await browser.close()
        
        return all_articles
