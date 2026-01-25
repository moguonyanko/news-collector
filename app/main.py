from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import logging

from .config import get_settings
from .scraper import scrape_urls
from .summarizer import summarize_articles

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    settings = get_settings()
    # Join URLs for display in textarea
    urls_str = "\n".join(settings["urls"])
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "urls": urls_str,
        "default_days": settings["default_days"],
        "default_summary_length": settings["default_summary_length"],
        "default_target": settings["default_target"]
    })

@app.post("/collect", response_class=HTMLResponse)
async def collect(
    request: Request,
    urls: str = Form(...),
    days: int = Form(...),
    length: int = Form(...),
    target: str = Form(...)
):
    try:
        url_list = [u.strip() for u in urls.split("\n") if u.strip()]
        
        logger.info(f"Collecting from {len(url_list)} URLs. Days={days}, Target={target}")
        
        # Scrape
        articles = await scrape_urls(url_list, days, target)
        
        if not articles:
            return templates.TemplateResponse("results.html", {
                "request": request,
                "error": "指定された条件に一致する記事が見つからないか、スクレイピングに失敗しました。"
            })
            
        # Limit the number of articles
        settings = get_settings()
        max_articles = settings.get("max_articles", 10)
        articles = articles[:max_articles]
        
        # Summarize
        summarized = summarize_articles(articles, target, length)
        
        return templates.TemplateResponse("results.html", {
            "request": request,
            "articles": summarized
        })
        
    except Exception as e:
        logger.exception("Error in /collect")
        return templates.TemplateResponse("results.html", {
            "request": request,
            "error": f"An unexpected error occurred: {str(e)}"
        })
