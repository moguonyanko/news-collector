from google import genai
from google.genai import types
import os
import logging
from .config import get_settings

logger = logging.getLogger(__name__)

def summarize_articles(articles: list[dict], genre: str, length: int) -> list[dict]:
    settings = get_settings()
    api_key = settings["gemini_api_key"]
    
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        logger.warning("Gemini API Key not set. Returning mock summaries.")
        # Return mock if no key
        for article in articles:
            article["summary"] = f"[MOCK SUMMARY] (API Key missing) This is a summary of {article['title']}. content length: {len(article['content'])}"
        return articles

    client = genai.Client(api_key=api_key)
    model_name = settings["gemini_model"]

    summarized_articles = []
    
    for article in articles:
        try:
            prompt = f"""
            You are a professional security news analyst.
            Summarize the following security news article for a "{genre}" audience.
             The summary should be approximately {length} characters long.
             If the article is not related to cybersecurity, output "IRRELEVANT".
             
             Title: {article['title']}
             Content: {article['content'][:5000]}
            """
            
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                summary_text = response.text.strip()
            except Exception as e:
                logger.error(f"Error with model {model_name}: {e}")
                
                # Fallback logic
                if "404" in str(e) or "not found" in str(e).lower():
                    try:
                        logger.warning(f"Model {model_name} not found. Trying gemini-1.5-flash.")
                        fallback_model = "gemini-1.5-flash"
                        response = client.models.generate_content(
                            model=fallback_model,
                            contents=prompt
                        )
                        summary_text = response.text.strip()
                    except Exception as fallback_e:
                        logger.error(f"Fallback model also failed: {fallback_e}")
                        # Final fallback: Use truncated content
                        summary_text = article['content'][:length] + "..."
                        article["summary_note"] = " (Auto-generated summary unavailable)"
                else:
                    # For other errors (like 429), go straight to truncation
                    logger.error(f"API Error (likely 429 or other): {e}")
                    summary_text = article['content'][:length] + "..."
                    article["summary_note"] = " (Auto-generated summary unavailable)"
            
            if "IRRELEVANT" in summary_text:
                continue
                
            article["summary"] = summary_text
            summarized_articles.append(article)
            
        except Exception as e:
            logger.error(f"Error summarizing article {article['title']}: {e}")
            # Absolute final fallback
            article["summary"] = article['content'][:length] + "..."
            summarized_articles.append(article)
            
    return summarized_articles
