from google import genai
import json
import logging
from .config import get_settings

logger = logging.getLogger(__name__)

def summarize_articles(articles: list[dict], target: str, length: int) -> list[dict]:
    settings = get_settings()
    api_key = settings["gemini_api_key"]
    
    if not api_key:
        raise ValueError("Gemini API Key is missing in settings")

    client = genai.Client(api_key=api_key)
    model_name = settings["gemini_model"]

    summarized_articles = []
    
    for article in articles:
        try:
            prompt = f"""
            You are a professional news analyst.
            Summarize the following news article for a "{target}" audience.
             The summary should be approximately {length} characters long.
             The output MUST be in Japanese.
             Also translate the title to Japanese.
             
             Return a JSON object with the following keys:
             - japanese_title: The translated title
             - japanese_summary: The summary in Japanese
             
             Title: {article['title']}
             Content: {article['content'][:5000]}
            """
            
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                summary_text = data.get("japanese_summary", "")
                article["title"] = data.get("japanese_title", article["title"])

            except Exception as e:
                logger.error(f"Error with model {model_name}: {e}")
                
                # Fallback to default model if different
                default_model = settings["default_gemini_model"]
                if model_name != default_model:
                    try:
                        logger.warning(f"Falling back to default model: {default_model}")
                        response = client.models.generate_content(
                            model=default_model,
                            contents=prompt,
                            config={"response_mime_type": "application/json"}
                        )
                        data = json.loads(response.text)
                        summary_text = data.get("japanese_summary", "")
                        article["title"] = data.get("japanese_title", article["title"])
                    except Exception as e2:
                        logger.error(f"Error with fallback model {default_model}: {e2}")
                        summary_text = article['content'][:length] + "..."
                        article["summary_note"] = " (Auto-generated summary unavailable)"
                else:
                    summary_text = article['content'][:length] + "..."
                    article["summary_note"] = " (Auto-generated summary unavailable)"
            
            if "IRRELEVANT" in summary_text:
                continue
                
            article["summary"] = summary_text
            summarized_articles.append(article)
            
        except Exception as e:
            logger.error(f"Error summarizing article {article['title']}: {e}")
            raise e
            
    return summarized_articles
