import jmespath
import asyncio
import json
from urllib.parse import urlencode
from typing import List, Dict
from httpx import AsyncClient, Response
from loguru import logger as log

client = AsyncClient(
    # enable http2
    http2=True,
    headers={
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "content-type": "application/json"
    },
)

def parse_comments(response: Response) -> Dict:
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        log.error(f"Failed to parse JSON response: {response.text}")
        return {"comments": [], "total_comments": 0}

    comments_data = data.get("comments", [])
    total_comments = data.get("total", 0)

    if not comments_data:
        log.warning(f"No comments found in response: {response.text}")
        return {"comments": [], "total_comments": total_comments}

    parsed_comments = []
    for comment in comments_data:
        result = jmespath.search(
            """{
            text: text,
            comment_language: comment_language,
            digg_count: digg_count,
            reply_comment_total: reply_comment_total,
            author_pin: author_pin,
            create_time: create_time,
            cid: cid,
            nickname: user.nickname,
            unique_id: user.unique_id,
            aweme_id: aweme_id
            }""",
            comment
        )
        parsed_comments.append(result)
    return {"comments": parsed_comments, "total_comments": total_comments}

async def scrape_comments(post_id: int, comments_count: int = 20, max_comments: int = None) -> List[Dict]:
    
    def form_api_url(cursor: int):
        base_url = "https://www.tiktok.com/api/comment/list/?"
        params = {
            "aweme_id": post_id,
            'count': comments_count,
            'cursor': cursor # the index to start from      
        }
        return base_url + urlencode(params)
    
    log.info(f"Scraping comments from post ID: {post_id}")
    first_page = await client.get(form_api_url(0))
    data = parse_comments(first_page)
    comments_data = data["comments"]
    total_comments = data["total_comments"]

    if not comments_data:
        log.warning(f"No comments found for post ID {post_id}")
        return []
    if max_comments and max_comments < total_comments:
        total_comments = max_comments

    log.info(f"Scraping comments pagination, remaining {total_comments // comments_count - 1} more pages")
    _other_pages = [
        client.get(form_api_url(cursor=cursor))
        for cursor in range(comments_count, total_comments + comments_count, comments_count)
    ]

    for response in asyncio.as_completed(_other_pages):
        response = await response
        new_comments = parse_comments(response)["comments"]
        comments_data.extend(new_comments)
        
        # If we have reached or exceeded the maximum number of comments to scrape, stop the process
        if max_comments and len(comments_data) >= max_comments:
            comments_data = comments_data[:max_comments]
            break

    log.success(f"Scraped {len(comments_data)} comments from post ID {post_id}")
    return comments_data

async def run():
    with open('project/tiktok.json', 'r', encoding='utf-8') as file:
        data = json.load(file)

    all_post_ids = []
    for user_posts in data.values():
        all_post_ids.extend(user_posts)
    all_comments_by_post_id = {}

    for post_id in all_post_ids:
        comments = await scrape_comments(
            post_id=int(post_id),
            max_comments=100,
            comments_count=20
        )
        all_comments_by_post_id[post_id] = comments
    
    with open("project/all_comments_by_post_id.json", "w", encoding="utf-8") as file:
        json.dump(all_comments_by_post_id, file, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(run())
